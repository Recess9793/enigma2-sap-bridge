import asyncio
import hashlib
import ipaddress
import logging
import socket
import struct

log = logging.getLogger("sap")


def sdp(origin_ip, channel_name, multicast, port):
    safe = channel_name.replace("\r", " ").replace("\n", " ")
    session_id = int.from_bytes(hashlib.md5(f"{safe}|{multicast}|{port}".encode()).digest()[:4], "big")
    return ("v=0\r\n" f"o=- {session_id} 1 IN IP4 {origin_ip}\r\n" f"s={safe}\r\n"
            "i=Enigma2 MPEG-TS\r\n" f"c=IN IP4 {multicast}/255\r\n" "t=0 0\r\n"
            f"m=video {port} RTP/AVP 33\r\n" "a=rtpmap:33 MP2T/90000\r\n"
            "a=type:broadcast\r\n" "a=tool:enigma2-sap-bridge\r\n").encode()


def sap_packet(origin_ip, channel_name, multicast, port):
    payload = b"application/sdp\x00" + sdp(origin_ip, channel_name, multicast, port)
    msg_id_hash = struct.unpack("!H", hashlib.md5(payload).digest()[:2])[0]
    return struct.pack("!BBHI", 0x20, 0, msg_id_hash, int(ipaddress.ip_address(origin_ip))) + payload


class SAPAnnouncer:
    def __init__(self, origin_ip, group, port, interval):
        self.origin_ip, self.group, self.port, self.interval = origin_ip, group, port, interval
        self.sessions, self.task, self.sock = {}, None, None

    async def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.origin_ip))
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.sock:
            self.sock.close()

    def set_sessions(self, sessions):
        self.sessions = dict(sessions)

    async def _loop(self):
        announced = -1
        while True:
            if len(self.sessions) != announced:
                announced = len(self.sessions)
                log.info("SAP: announcing %d session(s) via %s:%s", announced, self.group, self.port)
            for channel in list(self.sessions.values()):
                try:
                    self.sock.sendto(sap_packet(self.origin_ip, channel.name, channel.multicast, channel.port), (self.group, self.port))
                except Exception:
                    log.exception("SAP announcement failed for %s", channel.name)
                await asyncio.sleep(0.03)
            await asyncio.sleep(self.interval)
