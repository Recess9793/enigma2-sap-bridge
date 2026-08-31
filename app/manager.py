import asyncio
import ipaddress
import logging
from .models import Channel

log = logging.getLogger("manager")

class Manager:
    def __init__(self, enigma2, vlc, sap, default_bouquet):
        self.enigma2 = enigma2
        self.vlc = vlc
        self.sap = sap
        self.default_bouquet = default_bouquet
        self.bouquets = []
        self.channels = {}
        self.selected_bouquet = default_bouquet
        self.clients = {}  # service_ref -> set(client-id)
        self.lock = asyncio.Lock()

    async def refresh(self):
        bouquets = await self.enigma2.bouquets()
        self.bouquets = bouquets
        if not bouquets:
            raise RuntimeError("OpenWebif returned no TV bouquets")
        refs = {b["ref"] for b in bouquets}
        if self.selected_bouquet not in refs:
            self.selected_bouquet = bouquets[0]["ref"]
        await self.load_bouquet(self.selected_bouquet)

    async def load_bouquet(self, ref):
        async with self.lock:
            raw = await self.enigma2.channels(ref)
            self.channels = {}
            for idx, c in enumerate(raw):
                ch = Channel(c["ref"], c["name"], ref)
                ch.multicast = self._multicast(idx)
                ch.port = 5000 + idx * 2
                self.channels[ch.service_ref] = ch
            self.selected_bouquet = ref
            self._update_sap()

    def _multicast(self, idx):
        return str(ipaddress.ip_address(self.vlc.multicast_base) + idx)

    def _update_sap(self):
        self.sap.set_sessions(self.channels)

    async def join(self, group, client=""):
        ch = next((c for c in self.channels.values() if c.multicast == group), None)
        if not ch:
            log.debug("IGMP join for unknown group %s from %s", group, client)
            return
        clients = self.clients.setdefault(ch.service_ref, set())
        was_empty = not clients
        clients.add(f"igmp:{client}")
        if was_empty:
            await self.vlc.start(ch)

    async def leave(self, group, client=""):
        ch = next((c for c in self.channels.values() if c.multicast == group), None)
        if not ch:
            return
        clients = self.clients.setdefault(ch.service_ref, set())
        clients.discard(f"igmp:{client}")
        if not clients:
            await self.vlc.stop(ch.service_ref)

    async def start(self, ref):
        ch = self.channels.get(ref)
        if not ch:
            raise KeyError(ref)
        self.clients.setdefault(ref, set()).add("web")
        return await self.vlc.start(ch)

    async def stop(self, ref):
        self.clients.pop(ref, None)
        await self.vlc.stop(ref)

    def channel_list(self):
        return list(self.channels.values())

    def stream_list(self):
        return list(self.vlc.streams.values())

    def client_count(self, ref):
        return len(self.clients.get(ref, set()))
