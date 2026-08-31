import asyncio
import hashlib
import ipaddress
import logging
import socket
import struct

log = logging.getLogger("sap")

def sdp(channel_name, multicast, port):
    # RTP/AVP payload 33 = MPEG-TS.
    safe = channel_name.replace("\r", " ").replace("\n", " ")
    return (
        "v=0\r\n"
        f"o=- {abs(hash((safe, multicast, port))) & 0xffffffff} 1 IN IP4 0.0.0.0\r\n"
        f"s={safe}\r\n"
        "i=Enigma2 MPEG-TS\r\n"
        f"c=IN IP4 {multicast}/255\r\n"
        "t=0 0\r\n"
        f"m=video {port} RTP/AVP 33\r\n"
        "a=rtpmap:33 MP2T/90000\r\n"
        "a=type:broadcast\r\n"
        f"a=tool:enigma2-sap-bridge\r\n"
    ).encode()

def sap_packet(origin_ip, channel_name, multicast, port):
    # RFC 2974 SAPv1, IPv4, no auth. Payload is SDP.
    payload = b"application/sdp\x00" + sdp(channel_name, multicast, port)
    digest = hashlib.md5(payload).digest()
    msg_id_hash = struct.unpack("!H", digest[:2])[0]
    header = struct.pack("!BBHI", 0x20, 0, msg_id_hash, int(ipaddress.ip_address(origin_ip)))
    return header + payload

class SAPAnnouncer:
    def __init__(self, origin_ip, group, port, interval):
        self.origin_ip = origin_ip
        self.group = group
        self.port = port
        self.interval = interval
        self.sessions = {}
        self.task = None
        self.sock = None

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
        while True:
            for s in list(self.sessions.values()):
                try:
                    pkt = sap_packet(self.origin_ip, s.channel_name, s.multicast, s.port)
                    self.sock.sendto(pkt, (self.group, self.port))
                except Exception:
                    log.exception("SAP announcement failed for %s", s.channel_name)
            await asyncio.sleep(self.interval)
