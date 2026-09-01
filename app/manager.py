import asyncio
import base64
import ipaddress
import logging
from .models import Channel

log = logging.getLogger("manager")


class Manager:
    def __init__(self, enigma2, streams, sap, settings):
        self.enigma2, self.streams, self.sap, self.settings = enigma2, streams, sap, settings
        self.bouquets, self.channels, self.remote_channels, self.clients = [], {}, {}, {}
        self.selected_bouquet = settings.default_bouquet
        self.lock = asyncio.Lock()

    @staticmethod
    def _remote_id(service_ref):
        return base64.urlsafe_b64encode(service_ref.encode()).decode().rstrip("=")

    async def refresh(self):
        self.bouquets = await self.enigma2.bouquets()
        if not self.bouquets:
            raise RuntimeError("OpenWebif returned no TV bouquets")
        refs = {b["ref"] for b in self.bouquets}
        if self.selected_bouquet not in refs:
            self.selected_bouquet = self.bouquets[0]["ref"]
        await self.load_bouquet(self.selected_bouquet)

    async def load_bouquet(self, ref):
        async with self.lock:
            raw = await self.enigma2.channels(ref)
            channels, remote = {}, {}
            for idx, item in enumerate(raw):
                source_ref, name = item["ref"], item["name"]
                lan = Channel(f"lan:{source_ref}", source_ref, name, ref, "lan", str(ipaddress.ip_address(self.settings.multicast_base) + idx), self.settings.multicast_port_start + idx * 2)
                channels[lan.key] = lan
                if self.settings.wifi_enabled:
                    wifi = Channel(f"wifi:{source_ref}", source_ref, f"{name} – WLAN 720p", ref, "wifi", str(ipaddress.ip_address(self.settings.wifi_multicast_base) + idx), self.settings.wifi_multicast_port_start + idx * 2)
                    channels[wifi.key] = wifi
                remote[self._remote_id(source_ref)] = Channel(f"remote:{source_ref}", source_ref, f"{name} – Remote 480p", ref, "remote")
            self.channels, self.remote_channels, self.selected_bouquet = channels, remote, ref
            self.sap.set_sessions(channels)

    async def join(self, group, client=""):
        channel = next((c for c in self.channels.values() if c.multicast == group), None)
        if not channel:
            return
        members = self.clients.setdefault(channel.key, set())
        if f"igmp:{client}" in members:
            return
        was_empty = not members
        members.add(f"igmp:{client}")
        if was_empty:
            await self.streams.start_multicast(channel)

    async def leave(self, group, client=""):
        channel = next((c for c in self.channels.values() if c.multicast == group), None)
        if not channel:
            return
        members = self.clients.setdefault(channel.key, set())
        members.discard(f"igmp:{client}")
        if not members:
            await self.streams.release_multicast(channel.key)

    async def start(self, key):
        channel = self.channels.get(key)
        if not channel:
            raise KeyError(key)
        self.clients.setdefault(key, set()).add("web")
        return await self.streams.start_multicast(channel)

    async def stop(self, key):
        self.clients.pop(key, None)
        await self.streams.stop(key)

    async def start_remote(self, remote_id):
        channel = self.remote_channels.get(remote_id)
        if not channel:
            raise KeyError(remote_id)
        return await self.streams.start_hls(channel)

    def touch_remote(self, remote_id):
        self.streams.touch(f"remote:{self.remote_channels[remote_id].service_ref}")

    def channel_list(self): return list(self.channels.values())
    def stream_list(self): return list(self.streams.streams.values())
    def client_count(self, key): return len(self.clients.get(key, set()))
