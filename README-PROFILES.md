# Profil-Erweiterung

Diese Dateien ergänzen das vorhandene Projekt um LAN-, WLAN- und Remote-HLS-Profile.

## Installation

1. Im bestehenden Projekt vorher ein Backup erstellen.
2. Die Dateien aus diesem Paket in das Projektverzeichnis kopieren.
3. Die bisherige `.env` sichern und anhand von `.env.example` ergänzen. `REMOTE_TOKEN` mit `openssl rand -hex 32` erzeugen.
4. `docker compose up -d --build` ausführen.

## Nutzung

* LAN: SAP-Eintrag ohne Suffix; Original-TS in `239.192.7.0/24`.
* WLAN: SAP-Eintrag mit `– WLAN 720p`; H.264/AAC in `239.192.8.0/24`.
* Remote: Im Webinterface die Remote-ID kopieren und die HLS-URL mit NetBird-IP und Token in VLC öffnen.

Remote-HLS ist absichtlich nicht als SAP-Stream verfügbar. Der Zugriff ist für NetBird (oder ähnliches VPN Netzwerk, wie Tailscale,...) vorgesehen; der Token verhindert zusätzlich unabsichtliche Abrufe. Der Token ist kein Ersatz für NetBird-ACLs oder TLS.
