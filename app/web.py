import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from .config import settings
from .enigma2 import Enigma2Client
from .sap import SAPAnnouncer
from .stream import VLCStreamManager
from .manager import Manager
from .igmp import IGMPMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("web")

e2 = Enigma2Client(
    settings.enigma2_host, settings.enigma2_port,
    settings.enigma2_user, settings.enigma2_password
)

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((settings.enigma2_host, 80))
        return s.getsockname()[0]
    finally:
        s.close()

origin_ip = local_ip()
sap = SAPAnnouncer(origin_ip, settings.sap_group, settings.sap_port, settings.sap_interval)
vlc = VLCStreamManager(
    e2, settings.multicast_base, settings.multicast_port_start,
    settings.vlc_network_caching, settings.stream_stop_delay
)
manager = Manager(e2, vlc, sap, settings.default_bouquet)

async def on_join(group, client):
    await manager.join(group, client)

async def on_leave(group, client):
    await manager.leave(group, client)

async def refresh_loop():
    while True:
        await asyncio.sleep(settings.bouquet_refresh)
        try:
            await manager.refresh()
        except Exception as exc:
            log.warning("Periodic bouquet refresh failed: %s", exc)

igmp = IGMPMonitor(settings.igmp_interface, on_join, on_leave)

templates = Jinja2Templates(directory="/app/app/templates")

@asynccontextmanager
async def lifespan(app):
    await sap.start()
    try:
        await manager.refresh()
    except Exception as exc:
        log.error("Initial OpenWebif refresh failed: %s", exc)
    await igmp.start()
    refresh_task = asyncio.create_task(refresh_loop())
    yield
    refresh_task.cancel()
    await asyncio.gather(refresh_task, return_exceptions=True)
    await igmp.stop()
    await vlc.stop_all()
    await sap.stop()

app = FastAPI(title="Enigma2 SAP Bridge", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ok, msg = await e2.check()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "e2_ok": ok,
            "e2_msg": msg,
            "bouquets": manager.bouquets,
            "selected": manager.selected_bouquet,
            "channels": manager.channel_list(),
            "streams": {s.service_ref: s for s in manager.stream_list()},
            "igmp": igmp.running,
            "origin_ip": origin_ip,
            "settings": settings,
        },
    )

@app.post("/refresh")
async def refresh():
    try:
        await manager.refresh()
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return RedirectResponse("/", status_code=303)

@app.post("/bouquet")
async def bouquet(ref: str):
    try:
        await manager.load_bouquet(ref)
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return RedirectResponse("/", status_code=303)

@app.post("/stream/{service_ref:path}/start")
async def start_stream(service_ref: str):
    try:
        s = await manager.start(service_ref)
    except KeyError:
        raise HTTPException(404, "Service not found")
    return RedirectResponse("/", status_code=303)

@app.post("/stream/{service_ref:path}/stop")
async def stop_stream(service_ref: str):
    await manager.stop(service_ref)
    return RedirectResponse("/", status_code=303)

@app.post("/stop-all")
async def stop_all():
    await vlc.stop_all()
    return RedirectResponse("/", status_code=303)

@app.get("/playlist.m3u", response_class=PlainTextResponse)
async def playlist():
    lines = ["#EXTM3U"]
    for c in manager.channel_list():
        lines += [
            f'#EXTINF:-1,{c.name}',
            f'rtp://{c.multicast}:{c.port}',
        ]
    return "\n".join(lines) + "\n"

@app.get("/health")
async def health():
    ok, msg = await e2.check()
    return {
        "ok": ok,
        "enigma2": msg,
        "channels": len(manager.channel_list()),
        "streams": len(manager.stream_list()),
        "igmp_monitor": igmp.running,
        "origin_ip": origin_ip,
    }
