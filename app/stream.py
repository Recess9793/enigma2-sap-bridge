import asyncio
import logging
import os
import shutil
import signal
import time
from pathlib import Path
from .models import Stream

log = logging.getLogger("stream")


class StreamManager:
    def __init__(self, enigma2, settings):
        self.enigma2, self.settings = enigma2, settings
        self.streams = {}
        self.hls_root = Path("/data/hls")
        self.hls_root.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()

    def _source_url(self, channel):
        return self.enigma2.stream_url(channel.service_ref)

    def _env(self):
        env = dict(os.environ)
        env["HOME"] = "/data"
        return env

    async def _spawn(self, key, channel, cmd, kind):
        async with self.lock:
            current = self.streams.get(key)
            if current:
                current.last_access = time.monotonic()
                return current
            log.info("Starting %s stream: %s", channel.profile, " ".join(cmd))
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=self._env())
            stream = Stream(key, channel.service_ref, channel.name, channel.profile, kind, channel.multicast, channel.port, proc.pid)
            self.streams[key] = stream
            asyncio.create_task(self._watch(key, proc))
            return stream

    async def _watch(self, key, proc):
        _, stderr = await proc.communicate()
        log.info("Stream %s PID %s exited with %s", key, proc.pid, proc.returncode)
        if stderr:
            log.warning("Stream %s stderr: %s", key, stderr.decode(errors="replace")[-2000:].strip())
        self.streams.pop(key, None)

    async def start_multicast(self, channel):
        if channel.profile == "lan":
            cmd = ["setpriv", "--reuid=bridge", "--regid=bridge", "--clear-groups", "vlc", "-I", "dummy", "--quiet", "--network-caching", str(self.settings.vlc_network_caching), "--demux", "ts", self._source_url(channel), "--sout", f"#rtp{{dst={channel.multicast},port={channel.port},mux=ts}}"]
            return await self._spawn(channel.key, channel, cmd, "rtp")
        vf = f"scale=w={self.settings.wifi_width}:h={self.settings.wifi_height}:force_original_aspect_ratio=decrease,pad={self.settings.wifi_width}:{self.settings.wifi_height}:(ow-iw)/2:(oh-ih)/2"
        b = self.settings.wifi_video_bitrate_k
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-i", self._source_url(channel), "-map", "0:v:0", "-map", "0:a?", "-vf", vf, "-r", str(self.settings.wifi_fps), "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-b:v", f"{b}k", "-maxrate", f"{b}k", "-bufsize", f"{b * 2}k", "-g", str(self.settings.wifi_fps * 2), "-c:a", "aac", "-b:a", f"{self.settings.wifi_audio_bitrate_k}k", "-ac", "2", "-f", "rtp_mpegts", f"rtp://{channel.multicast}:{channel.port}?ttl=16"]
        return await self._spawn(channel.key, channel, cmd, "rtp")

    async def start_hls(self, channel):
        key = channel.key
        directory = self.hls_root / key.replace(":", "_")
        if key not in self.streams:
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True, exist_ok=True)
        vf = f"scale=w={self.settings.remote_width}:h={self.settings.remote_height}:force_original_aspect_ratio=decrease,pad={self.settings.remote_width}:{self.settings.remote_height}:(ow-iw)/2:(oh-ih)/2"
        b = self.settings.remote_video_bitrate_k
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-i", self._source_url(channel), "-map", "0:v:0", "-map", "0:a?", "-vf", vf, "-r", str(self.settings.remote_fps), "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-b:v", f"{b}k", "-maxrate", f"{b}k", "-bufsize", f"{b * 2}k", "-g", str(self.settings.remote_fps * 2), "-c:a", "aac", "-b:a", f"{self.settings.remote_audio_bitrate_k}k", "-ac", "2", "-f", "hls", "-hls_time", str(self.settings.remote_hls_segment_seconds), "-hls_list_size", str(self.settings.remote_hls_list_size), "-hls_flags", "delete_segments+append_list+independent_segments", "-hls_segment_filename", str(directory / "seg_%06d.ts"), str(directory / "index.m3u8")]
        return await self._spawn(key, channel, cmd, "hls")

    def hls_file(self, key, filename):
        path = (self.hls_root / key.replace(":", "_") / filename).resolve()
        root = (self.hls_root / key.replace(":", "_")).resolve()
        if root not in path.parents and path != root:
            return None
        return path if path.is_file() else None

    def touch(self, key):
        stream = self.streams.get(key)
        if stream:
            stream.last_access = time.monotonic()

    async def release_multicast(self, key):
        await asyncio.sleep(self.settings.stream_stop_delay)
        stream = self.streams.get(key)
        if stream:
            await self.stop(key)

    async def reap_hls(self):
        while True:
            await asyncio.sleep(5)
            now = time.monotonic()
            for key, stream in list(self.streams.items()):
                if stream.kind == "hls" and now - stream.last_access > self.settings.remote_idle_timeout:
                    log.info("Stopping idle remote HLS stream %s", key)
                    await self.stop(key)

    async def stop(self, key):
        stream = self.streams.pop(key, None)
        if not stream or not stream.pid:
            return
        try:
            os.kill(stream.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    async def stop_all(self):
        for key in list(self.streams):
            await self.stop(key)
