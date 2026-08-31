import asyncio
import logging
import os
import signal

log = logging.getLogger("stream")

class VLCStreamManager:
    def __init__(self, enigma2, multicast_base, port_start, caching, stop_delay):
        self.enigma2 = enigma2
        self.multicast_base = multicast_base
        self.port_start = port_start
        self.caching = caching
        self.stop_delay = stop_delay
        self.streams = {}
        self.port_used = set()

    def allocate(self, channel, index):
        if not channel.multicast:
            channel.multicast = self._multicast(index)
        if not channel.port:
            channel.port = self._port(index)
        return channel

    def _multicast(self, index):
        import ipaddress
        return str(ipaddress.ip_address(self.multicast_base) + index)

    def _port(self, index):
        # RTP uses an even UDP port; keep a simple deterministic mapping.
        return self.port_start + index * 2

    async def start(self, channel):
        if channel.service_ref in self.streams:
            self.streams[channel.service_ref].clients += 1
            return self.streams[channel.service_ref]

        url = self.enigma2.stream_url(channel.service_ref)
        sout = (
            f"#rtp{{dst={channel.multicast},port={channel.port},mux=ts}}"
        )
        cmd = [
            "cvlc", "--intf", "dummy", "--quiet",
            "--network-caching", str(self.caching),
            "--demux", "ts",
            url,
            "--sout", sout,
        ]
        log.info("Starting VLC: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        from .models import Stream
        stream = Stream(
            service_ref=channel.service_ref,
            channel_name=channel.name,
            multicast=channel.multicast,
            port=channel.port,
            pid=proc.pid,
            clients=1,
        )
        self.streams[channel.service_ref] = stream
        asyncio.create_task(self._watch(channel.service_ref, proc))
        return stream

    async def _watch(self, ref, proc):
        rc = await proc.wait()
        log.info("VLC PID %s exited with %s", proc.pid, rc)
        self.streams.pop(ref, None)

    async def release(self, service_ref):
        s = self.streams.get(service_ref)
        if not s:
            return
        s.clients = max(0, s.clients - 1)
        if s.clients:
            return
        await asyncio.sleep(self.stop_delay)
        s2 = self.streams.get(service_ref)
        if not s2 or s2.clients:
            return
        await self.stop(service_ref)

    async def stop(self, service_ref):
        s = self.streams.pop(service_ref, None)
        if not s or not s.pid:
            return
        try:
            os.kill(s.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    async def stop_all(self):
        for ref in list(self.streams):
            await self.stop(ref)
