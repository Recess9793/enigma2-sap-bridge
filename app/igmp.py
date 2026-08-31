import asyncio
import logging

from scapy.all import sniff, IP
# Scapy 2.6.x: IGMP liegt NICHT in scapy.layers.inet.
# - IGMP (v1/v2)        -> scapy.contrib.igmp
# - IGMPv3 / IGMPv3mr   -> scapy.contrib.igmpv3
# (Erst ab Scapy 2.7+ existiert scapy.layers.igmp.)
from scapy.contrib.igmp import IGMP
from scapy.contrib.igmpv3 import IGMPv3mr

log = logging.getLogger("igmp")


class IGMPMonitor:
    """
    Beobachtet IGMP Membership Reports auf dem LAN-Interface.

    Unterstützt:
      - IGMPv1 Membership Report
      - IGMPv2 Membership Report
      - IGMPv2 Leave
      - IGMPv3 Membership Report

    Hinweis:
    Bei IGMP Snooping kann ein Switch die Reports lokal verarbeiten,
    sodass sie möglicherweise nicht im LXC sichtbar werden.
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

        self.task = asyncio.create_task(
            asyncio.to_thread(self._sniff)
        )

        log.info(
            "IGMP monitor started on %s",
            self.interface or "automatic interface selection",
        )

    async def stop(self):
        self.running = False

        if self.task:
            # Der Sniff-Thread laeuft in to_thread() und laesst sich nicht
            # per task.cancel() abbrechen; stop_filter wird erst beim
            # naechsten Paket geprueft. Deshalb nur begrenzt warten,
            # damit der Container-Shutdown nicht haengt.
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.task),
                    timeout=2.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass
            self.task = None

    def _sniff(self):
        try:
            sniff(
                iface=self.interface,
                filter="igmp",
                prn=self._packet,
                store=False,
                stop_filter=lambda packet: not self.running,
            )

        except Exception:
            log.exception(
                "IGMP packet capture failed. "
                "Automatic stream activation is unavailable."
            )

    def _dispatch(self, coroutine):
        if not self.loop:
            return

        asyncio.run_coroutine_threadsafe(
            coroutine,
            self.loop,
        )

    def _packet(self, packet):

        if not packet.haslayer(IP):
            return

        if not packet.haslayer(IGMP):
            return

        ip = packet[IP]
        igmp = packet[IGMP]

        client = ip.src

        # ------------------------------------------------------------
        # IGMPv1 / IGMPv2
        # ------------------------------------------------------------

        group = getattr(igmp, "gaddr", None)

        if group and str(group) != "0.0.0.0":

            # Membership Report:
            #
            # IGMPv1 = 0x12
            # IGMPv2 = 0x16
            #
            if igmp.type in (0x12, 0x16):

                log.info(
                    "IGMP JOIN: %s -> %s",
                    client,
                    group,
                )

                self._dispatch(
                    self.on_join(
                        str(group),
                        client,
                    )
                )

                return

            # IGMPv2 Leave
            if igmp.type == 0x17:

                log.info(
                    "IGMP LEAVE: %s -> %s",
                    client,
                    group,
                )

                self._dispatch(
                    self.on_leave(
                        str(group),
                        client,
                    )
                )

                return

        # ------------------------------------------------------------
        # IGMPv3
        # ------------------------------------------------------------

        if igmp.type == 0x22:

            # Scapy 2.6.x: die Group Records liegen im IGMPv3mr-Payload
            # (IGMPv3mr = "Membership Report", gebunden an IGMPv3 type=0x22),
            # nicht direkt auf dem IGMPv3-Layer.
            mr = packet.getlayer(IGMPv3mr)
            if mr is not None:
                records = list(mr.records)
            else:
                # Fallback fuer andere Scapy-Layouts
                records = list(getattr(igmp, "records", None) or [])

            if not records:
                log.debug(
                    "IGMPv3 report from %s without records",
                    client,
                )
                return

            for record in records:

                group = getattr(
                    record,
                    "maddr",
                    None,
                )

                if not group:
                    continue

                record_type = getattr(
                    record,
                    "rtype",
                    None,
                )

                # IGMPv3 record types:
                #
                # 1 MODE_IS_INCLUDE
                # 2 MODE_IS_EXCLUDE
                # 3 CHANGE_TO_INCLUDE_MODE
                # 4 CHANGE_TO_EXCLUDE_MODE
                # 5 ALLOW_NEW_SOURCES
                # 6 BLOCK_OLD_SOURCES
                #
                # Fuer unsere Anwendung behandeln wir JOIN-relevante
                # Zustaende als Membership und Leave/Block als Release.

                if record_type in (1, 2, 4, 5):

                    log.info(
                        "IGMPv3 JOIN: %s -> %s (rtype=%s)",
                        client,
                        group,
                        record_type,
                    )

                    self._dispatch(
                        self.on_join(
                            str(group),
                            client,
                        )
                    )

                elif record_type in (3, 6):

                    log.info(
                        "IGMPv3 LEAVE: %s -> %s (rtype=%s)",
                        client,
                        group,
                        record_type,
                    )

                    self._dispatch(
                        self.on_leave(
                            str(group),
                            client,
                        )
                    )
