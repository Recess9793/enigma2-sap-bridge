# Webinterface-Update

Die Startseite zeigt nur native LAN-Sender, `/wifi` nur WLAN-720p-Sender und `/remote` die HLS-Remote-Links. Die M3U-Dateien sind getrennt verfügbar.

Für eine Remote-M3U, die auch unterwegs sofort korrekt ist, `REMOTE_PUBLIC_BASE_URL` in `.env` auf die NetBird-IP (oder NetBird-DNS-Adresse) des Bridge-LXC setzen. Beispiel: `REMOTE_PUBLIC_BASE_URL=http://100.64.12.34:8090`.

Die HLS-M3U enthält den Remote-Token. Sie nur auf eigenen, vertrauenswürdigen Geräten speichern und nicht weitergeben.
