# Enigma2 SAP Bridge

Docker-Compose-Projekt für einen OpenATV/Enigma2-Receiver und einen Proxmox-LXC.

## Ziel

- OpenWebif-Bouquets vom Enigma2-Receiver einlesen
- TV-Bouquet im Webinterface auswählen
- SAP-Ankündigungen für die Sender erzeugen
- pro Sender eine feste RTP/UDP-Multicast-Adresse bereitstellen
- bei erkanntem IGMP Membership Report VLC/CVLc starten
- MPEG-TS ohne Transcoding vom Enigma2-Receiver weiterreichen
- nach dem letzten Leave VLC automatisch stoppen
- manuelle Start/Stop-Steuerung im Webinterface
- M3U-Playlist als Fallback

## Architektur

Receiver:
  192.168.7.122

LXC:
  192.168.7.38

Webinterface:
  http://192.168.7.38:8090

SAP:
  224.2.127.254:9875

Multicast:
  239.192.7.100/24

## Voraussetzungen

1. Proxmox LXC mit Docker/Docker Compose.
2. Netzwerkinterface des LXC muss Multicast unterstützen.
3. OpenWebif muss auf dem Enigma2-Receiver erreichbar sein.
4. Der Receiver muss HTTP-Streaming auf Port 8001 erlauben.
5. Switch/AP sollte Multicast/IGMP korrekt weiterleiten.

## Installation

```bash
mkdir -p /opt/enigma2-sap-bridge
cd /opt/enigma2-sap-bridge
# Projektdateien hierher kopieren
cp .env.example .env
nano .env
docker compose build
docker compose up -d
docker compose logs -f
```

Webinterface:
http://192.168.7.38:8090

Health:
http://192.168.7.38:8090/health

M3U:
http://192.168.7.38:8090/playlist.m3u

## OpenWebif

Der Code verwendet die OpenWebif-AJAX-Endpunkte `/ajax/bouquets` und
`/ajax/channels`. OpenWebif-Varianten können unterschiedliche JSON-Formate
liefern; die Normalisierung im Client fängt die üblichen Formen ab.

Wenn `/ajax/bouquets` bei deiner Version nicht verfügbar ist, kann der
Bouquet-Adapter leicht auf den konkreten OpenWebif-Endpunkt angepasst werden.

## IGMP

Die automatische Start/Stop-Funktion basiert auf dem Beobachten von IGMP
Membership Reports.

Das ist bewusst als best-effort implementiert: bei einem IGMP-Snooping-Switch
kann es passieren, dass der Report nicht am LXC ankommt. Dann funktioniert
die manuelle Start/Stop-Funktion weiterhin.

Für einen zuverlässigen Betrieb kann `IGMP_INTERFACE` z.B. auf `eth0`
gesetzt werden.

## Multicast/SAP

Die SAP-Ankündigungen werden vom Bridge-Dienst selbst erzeugt. Dadurch können
Sender angekündigt werden, obwohl der dazugehörige Enigma2-HTTP-Stream noch
nicht läuft.

Beim Join:
  VLC Mac -> IGMP Join -> Bridge -> VLC/CVLC -> Enigma2

Beim Leave:
  VLC Mac -> IGMP Leave -> Bridge -> Stop VLC nach STREAM_STOP_DELAY

## VLC

Der Stream wird nicht transkodiert. CVLC liest den MPEG-TS-Stream des
Enigma2-Receivers und gibt ihn als RTP/MPEG-TS Multicast aus.

Die `VLC_NETWORK_CACHING`-Einstellung steht standardmäßig auf 150 ms.
Bei Aussetzern kann man 250 oder 300 testen; für schnelles Umschalten eher
100-150.

## Wichtig: verschlüsselte Sender

Die Bridge entschlüsselt nichts. Der Receiver muss den gewünschten Service
selbst über seine Tuner/CI-Konfiguration streamen können.

Bei mehreren gleichzeitig angeforderten Sendern entscheidet die Tuner-
Konfiguration des Enigma2-Receivers, ob die gewünschten Transponder parallel
bedient werden können.

## Diagnose

```bash
docker compose ps
docker compose logs -f
curl http://192.168.7.38:8090/health
```

IGMP auf dem LXC prüfen:

```bash
tcpdump -ni eth0 igmp
```

Multicast prüfen:

```bash
ip maddr
ip route
```

Stream manuell starten:

```bash
curl -X POST \
  "http://192.168.7.38:8090/stream/SERVICE_REFERENCE/start"
```

Alle Streams stoppen:

```bash
curl -X POST http://192.168.7.38:8090/stop-all
```


## Proxmox/LXC-Hinweis

Dieses Projekt nutzt `network_mode: host` innerhalb des Docker-Containers,
damit SAP/IGMP/Multicast nicht durch ein zusätzliches Docker-Bridge-Netz
laufen.

Der Docker-Daemon muss im LXC funktionieren. Für automatische IGMP-Erkennung
benötigt der Container `NET_RAW`; der LXC/Proxmox-Host und dein Switch müssen
Multicast/IGMP zulassen.

Wenn `tcpdump -ni eth0 igmp` im LXC keine Membership Reports vom Mac zeigt,
ist das kein Python/VLC-Fehler: dann liefert die Netzwerkinfrastruktur die
Reports nicht bis zum LXC. In diesem Fall funktioniert die Web-Start/Stop-
Funktion weiterhin. Für einen vollständig automatischen Betrieb muss der
Switch/AP IGMP-Snooping so konfigurieren, dass die Reports am LXC sichtbar
sind.

## Erste Inbetriebnahme

1. Auf dem Receiver prüfen:
   `http://192.168.7.122/`
2. Im Webinterface des Bridges:
   `http://192.168.7.38:8090`
3. Bouquet auswählen und aktualisieren.
4. Prüfen:
   `http://192.168.7.38:8090/health`
5. VLC auf dem Mac öffnen und SAP im lokalen Netzwerk suchen.
6. Wenn der Sender sichtbar ist, anklicken.
7. Parallel:
   `docker compose logs -f`
   und
   `tcpdump -ni eth0 igmp`
   beobachten.

Falls SAP sichtbar ist, aber kein Bild kommt, zuerst im Bridge-Webinterface
den betreffenden Sender manuell mit `Start` aktivieren. Wenn dann Bild kommt,
ist der Enigma2→VLC-Pfad korrekt und nur die IGMP-Erkennung/Netzwerkseite muss
angepasst werden.

## Sicherheit

OpenWebif-Zugangsdaten können in `.env` gesetzt werden. Das Webinterface der
Bridge hat in dieser Version keine Benutzeranmeldung und sollte daher nur im
vertrauenswürdigen LAN erreichbar sein.
