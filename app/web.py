import asyncio
import logging
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .config import settings
from .enigma2 import Enigma2Client
from .igmp import IGMPMonitor
from .manager import Manager
from .sap import SAPAnnouncer
from .stream import StreamManager

log = logging.getLogger("web")


def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((settings.enigma2_host, 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


e2 = Enigma2Client(settings.enigma2_host, settings.enigma2_port, settings.enigma2_user, settings.enigma2_password)
origin_ip = local_ip()
sap = SAPAnnouncer(origin_ip, settings.sap_group, settings.sap_port, settings.sap_interval)
streams = StreamManager(e2, settings)
manager = Manager(e2, streams, sap, settings)
igmp = IGMPMonitor(settings.igmp_interface, manager.join, manager.leave)
templates = Jinja2Templates(directory="/app/app/templates")


async def refresh_loop():
    while True:
        await asyncio.sleep(settings.bouquet_refresh)
        try:
            await manager.refresh()
        except Exception:
            log.exception("Periodic bouquet refresh failed")


@asynccontextmanager
async def lifespan(app):
    await sap.start()
    try:
        await manager.refresh()
    except Exception:
        log.exception("Initial OpenWebif refresh failed")
    await igmp.start()
    refresh_task = asyncio.create_task(refresh_loop())
    reap_task = asyncio.create_task(streams.reap_hls())
    yield
    refresh_task.cancel()
    reap_task.cancel()
    await asyncio.gather(refresh_task, reap_task, return_exceptions=True)
    await igmp.stop()
    await streams.stop_all()
    await sap.stop()


app = FastAPI(title="Enigma2 SAP Bridge", lifespan=lifespan)


def remote_allowed(token):
    return bool(settings.remote_enabled and settings.remote_token and token == settings.remote_token)


def remote_base_url(request):
    configured = settings.remote_public_base_url.rstrip("/")
    return configured or str(request.base_url).rstrip("/")


async def render_channels(request, profile, title):
    ok, msg = await e2.check()
    channels = [channel for channel in manager.channel_list() if channel.profile == profile]
    return templates.TemplateResponse(
        "channels.html",
        {
            "request": request,
            "title": title,
            "active_page": profile,
            "e2_ok": ok,
            "e2_msg": msg,
            "bouquets": manager.bouquets,
            "selected": manager.selected_bouquet,
            "channels": channels,
            "streams": {stream.key: stream for stream in manager.stream_list()},
            "manager": manager,
            "igmp": igmp.running,
            "origin_ip": origin_ip,
            "settings": settings,
        },
    )


@app.get("/", response_class=HTMLResponse)
async def native_page(request: Request):
    return await render_channels(request, "lan", "Native LAN-Streams")


@app.get("/wifi", response_class=HTMLResponse)
async def wifi_page(request: Request):
    return await render_channels(request, "wifi", "WLAN-Streams (720p)")


@app.get("/remote", response_class=HTMLResponse)
async def remote_page(request: Request):
    ok, msg = await e2.check()
    return templates.TemplateResponse(
        "remote.html",
        {
            "request": request,
            "title": "Remote HLS-Streams (480p)",
            "active_page": "remote",
            "e2_ok": ok,
            "e2_msg": msg,
            "remote": manager.remote_channels,
            "streams": {stream.key: stream for stream in manager.stream_list()},
            "settings": settings,
            "base_url": remote_base_url(request),
        },
    )


@app.post("/refresh")
async def refresh():
    try:
        await manager.refresh()
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return RedirectResponse("/", 303)


@app.post("/bouquet")
async def bouquet(ref: str):
    try:
        await manager.load_bouquet(ref)
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return RedirectResponse("/", 303)


@app.post("/stream/{key:path}/start")
async def start_stream(key: str, request: Request):
    try:
        await manager.start(key)
    except KeyError:
        raise HTTPException(404, "Channel not found")
    return RedirectResponse(request.headers.get("referer", "/"), 303)


@app.post("/stream/{key:path}/stop")
async def stop_stream(key: str, request: Request):
    await manager.stop(key)
    return RedirectResponse(request.headers.get("referer", "/"), 303)


@app.post("/stop-all")
async def stop_all(request: Request):
    await streams.stop_all()
    return RedirectResponse(request.headers.get("referer", "/"), 303)


@app.get("/playlist.m3u", response_class=PlainTextResponse)
async def playlist(profile: str = "lan"):
    if profile not in ("lan", "wifi"):
        raise HTTPException(400, "profile must be lan or wifi")
    lines = ["#EXTM3U"]
    for channel in manager.channel_list():
        if channel.profile == profile:
            lines.extend((f"#EXTINF:-1,{channel.name}", f"rtp://@{channel.multicast}:{channel.port}"))
    return "\n".join(lines) + "\n"


@app.get("/remote/playlist.m3u", response_class=PlainTextResponse)
async def remote_playlist_download(request: Request, token: str = ""):
    if not remote_allowed(token):
        raise HTTPException(403, "Invalid remote token")
    base_url = remote_base_url(request)
    lines = ["#EXTM3U"]
    for remote_id, channel in manager.remote_channels.items():
        url = f"{base_url}/remote/{remote_id}/index.m3u8?token={token}"
        lines.extend((f"#EXTINF:-1,{channel.name}", url))
    return PlainTextResponse("\n".join(lines) + "\n", headers={"Content-Disposition": "attachment; filename=enigma2-remote-hls.m3u"})


@app.get("/remote/{remote_id}/index.m3u8")
async def remote_hls_playlist(remote_id: str, token: str = ""):
    if not remote_allowed(token):
        raise HTTPException(403, "Invalid remote token")
    try:
        await manager.start_remote(remote_id)
    except KeyError:
        raise HTTPException(404, "Channel not found")

    channel = manager.remote_channels[remote_id]

    # The first request starts ffmpeg. Do not return a temporary empty
    # playlist: VLC interprets it as a failed M3U item and skips ahead.
    # Wait up to 15 seconds for the first HLS segment instead.
    path = None
    text = ""
    for _ in range(30):
        path = streams.hls_file(channel.key, "index.m3u8")
        if path:
            text = path.read_text(errors="replace")
            if "#EXTINF:" in text:
                break
        await asyncio.sleep(0.5)
    else:
        raise HTTPException(
            504,
            "HLS startup timed out; check the bridge container log for ffmpeg errors",
        )

    manager.touch_remote(remote_id)
    text = re.sub(
        r"^(seg_[^\r\n]+\.ts)$",
        rf"/remote/{remote_id}/\1?token={token}",
        text,
        flags=re.MULTILINE,
    )
    return Response(
        text,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )

@app.get("/remote/{remote_id}/{filename}")
async def remote_hls_segment(remote_id: str, filename: str, token: str = ""):
    if not remote_allowed(token):
        raise HTTPException(403, "Invalid remote token")
    if not re.fullmatch(r"seg_\d+\.ts", filename):
        raise HTTPException(404)
    channel = manager.remote_channels.get(remote_id)
    if not channel:
        raise HTTPException(404)
    path = streams.hls_file(channel.key, filename)
    if not path:
        raise HTTPException(404)
    manager.touch_remote(remote_id)
    return FileResponse(path, media_type="video/mp2t", headers={"Cache-Control": "no-store"})


@app.get("/health")
async def health():
    ok, msg = await e2.check()
    return {"ok": ok, "enigma2": msg, "channels": len(manager.channel_list()), "streams": len(manager.stream_list()), "igmp_monitor": igmp.running, "origin_ip": origin_ip}
