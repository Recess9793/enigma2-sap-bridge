import asyncio
import logging

from scapy.all import IP, sniff
from scapy.contrib.igmp import IGMP
from scapy.contrib.igmpv3 import IGMPv3, IGMPv3mr

log = logging.getLogger("igmp")


class IGMPMonitor:
    """Observe IGMP membership reports and map them to bridge callbacks.

    Supports IGMPv1/v2 reports and leaves as well as IGMPv3 membership
    reports. Scapy 2.6.x exposes v1/v2 as ``IGMP`` and v3 as a separate
    ``IGMPv3`` layer, hence the separate parsing paths below.
    """

    def __init__(self, interface, on_join, on_leave):
        self.interface = interface or None
        self.on_join = on_join
        self.on_leave = on_leave
        self.task = None
        self.running = False
        self.loop = None

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.running = True
        self.task = asyncio.create_task(asyncio.to_thread(self._sniff))
        log.info(
            "IGMP monitor started on %s",
            self.interface or "automatic interface selection",
        )

    async def stop(self):
        self.running = False
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                log.exception("IGMP monitor shutdown failed")
            self.task = None

    def _sniff(self):
        try:
            sniff(
                iface=self.interface,
                filter="igmp",
                prn=self._packet,
                store=False,
                stop_filter=lambda _: not self.running,
            )
        except Exception:
            log.exception(
                "IGMP packet capture failed. "
                "Automatic stream activation is unavailable."
            )

    def _dispatch(self, coroutine):
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    @staticmethod
    def _bridge_group(group):
        """Only react to the multicast range owned by this bridge."""
        return group.startswith("239.192.7.")

    def _packet(self, packet):
        if not packet.haslayer(IP):
            return

        client = packet[IP].src

        # ------------------------------------------------------------
        # IGMPv3
        #
        # Windows VLC normally uses these reports. Unlike IGMPv1/v2,
        # the Scapy 2.6.x decoder does not expose them as the IGMP class.
        # A membership report (type 0x22) has IGMPv3mr group records.
        # ------------------------------------------------------------
        if packet.haslayer(IGMPv3):
            igmp3 = packet[IGMPv3]
            if igmp3.type != 0x22:
                return

            report = packet.getlayer(IGMPv3mr)
            records = list(getattr(report, "records", []) or [])
            if not records:
                # Fallback for a different Scapy packet layout.
                records = list(getattr(igmp3, "records", []) or [])

            if not records:
                log.debug(
                    "IGMPv3 report from %s without decoded group records",
                    client,
                )
                return

            for record in records:
                group = str(getattr(record, "maddr", "") or "")
                record_type = getattr(record, "rtype", None)

                if not group or not self._bridge_group(group):
                    continue

                # RFC 3376 record types:
                # 1 MODE_IS_INCLUDE
                # 2 MODE_IS_EXCLUDE
                # 3 CHANGE_TO_INCLUDE_MODE
                # 4 CHANGE_TO_EXCLUDE_MODE
                # 5 ALLOW_NEW_SOURCES
                # 6 BLOCK_OLD_SOURCES
                #
                # For any-source RTP multicast, VLC/Windows uses type 4
                # when opening a stream. Treat it, plus active membership
                # states, as a join. Type 3/6 are treated as a release.
                if record_type in (1, 2, 4, 5):
                    log.info(
                        "IGMPv3 JOIN: %s -> %s (rtype=%s)",
                        client,
                        group,
                        record_type,
                    )
                    self._dispatch(self.on_join(group, client))
                elif record_type in (3, 6):
                    log.info(
                        "IGMPv3 LEAVE: %s -> %s (rtype=%s)",
                        client,
                        group,
                        record_type,
                    )
                    self._dispatch(self.on_leave(group, client))
            return

        # ------------------------------------------------------------
        # IGMPv1 / IGMPv2
        #
        # macOS VLC in this network sends v2 reports directly to the
        # requested multicast group and v2 leaves to 224.0.0.2.
        # ------------------------------------------------------------
        if not packet.haslayer(IGMP):
            return

        igmp = packet[IGMP]
        group = str(getattr(igmp, "gaddr", "") or "")
        if not group or group == "0.0.0.0" or not self._bridge_group(group):
            return

        # IGMPv1 Membership Report = 0x12; IGMPv2 Membership Report = 0x16.
        if igmp.type in (0x12, 0x16):
            log.info("IGMP JOIN: %s -> %s", client, group)
            self._dispatch(self.on_join(group, client))
            return

        # IGMPv2 Leave = 0x17.
        if igmp.type == 0x17:
            log.info("IGMP LEAVE: %s -> %s", client, group)
            self._dispatch(self.on_leave(group, client))
