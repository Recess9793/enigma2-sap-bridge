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
    wifi_enabled: bool = env("WIFI_ENABLED", "1").lower() in ("1", "true", "yes", "on")
    wifi_multicast_base: str = env("WIFI_MULTICAST_BASE", "239.192.8.100")
    wifi_multicast_port_start: int = int(env("WIFI_MULTICAST_PORT_START", "6000"))
    wifi_width: int = int(env("WIFI_WIDTH", "1280"))
    wifi_height: int = int(env("WIFI_HEIGHT", "720"))
    wifi_fps: int = int(env("WIFI_FPS", "25"))
    wifi_video_bitrate_k: int = int(env("WIFI_VIDEO_BITRATE_K", "2500"))
    wifi_audio_bitrate_k: int = int(env("WIFI_AUDIO_BITRATE_K", "128"))
    remote_enabled: bool = env("REMOTE_ENABLED", "1").lower() in ("1", "true", "yes", "on")
    remote_width: int = int(env("REMOTE_WIDTH", "854"))
    remote_height: int = int(env("REMOTE_HEIGHT", "480"))
    remote_fps: int = int(env("REMOTE_FPS", "25"))
    remote_video_bitrate_k: int = int(env("REMOTE_VIDEO_BITRATE_K", "900"))
    remote_audio_bitrate_k: int = int(env("REMOTE_AUDIO_BITRATE_K", "96"))
    remote_hls_segment_seconds: int = int(env("REMOTE_HLS_SEGMENT_SECONDS", "2"))
    remote_hls_list_size: int = int(env("REMOTE_HLS_LIST_SIZE", "6"))
    remote_idle_timeout: int = int(env("REMOTE_IDLE_TIMEOUT", "45"))
    remote_token: str = env("REMOTE_TOKEN", "")
    remote_public_base_url: str = env("REMOTE_PUBLIC_BASE_URL", "")
    sap_group: str = env("SAP_GROUP", "224.2.127.254")
    sap_port: int = int(env("SAP_PORT", "9875"))
    sap_interval: int = int(env("SAP_INTERVAL", "10"))
    stream_stop_delay: int = int(env("STREAM_STOP_DELAY", "5"))
    vlc_network_caching: int = int(env("VLC_NETWORK_CACHING", "150"))
    igmp_interface: str = env("IGMP_INTERFACE", "eth0")
    bouquet_refresh: int = int(env("BOUQUET_REFRESH", "60"))
    default_bouquet: str = env("DEFAULT_BOUQUET", "userbouquet.favourites.tv")


settings = Settings()
