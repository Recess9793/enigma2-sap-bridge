import os
from dataclasses import dataclass

def env(name, default=""):
    return os.getenv(name, default)

@dataclass(frozen=True)
class Settings:
    enigma2_host: str = env("ENIGMA2_HOST", "192.168.7.122")
    enigma2_port: int = int(env("ENIGMA2_PORT", "80"))
    enigma2_user: str = env("ENIGMA2_USER", "")
    enigma2_password: str = env("ENIGMA2_PASSWORD", "")
    web_host: str = env("WEB_HOST", "0.0.0.0")
    web_port: int = int(env("WEB_PORT", "8090"))
    multicast_base: str = env("MULTICAST_BASE", "239.192.7.100")
    multicast_port_start: int = int(env("MULTICAST_PORT_START", "5000"))
    sap_group: str = env("SAP_GROUP", "224.2.127.254")
    sap_port: int = int(env("SAP_PORT", "9875"))
    sap_interval: int = int(env("SAP_INTERVAL", "10"))
    stream_stop_delay: int = int(env("STREAM_STOP_DELAY", "5"))
    vlc_network_caching: int = int(env("VLC_NETWORK_CACHING", "150"))
    igmp_interface: str = env("IGMP_INTERFACE", "")
    bouquet_refresh: int = int(env("BOUQUET_REFRESH", "60"))
    default_bouquet: str = env("DEFAULT_BOUQUET", "userbouquet.favourites.tv")

settings = Settings()
