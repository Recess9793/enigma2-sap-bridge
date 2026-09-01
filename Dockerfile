FROM debian:bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv vlc iproute2 procps ca-certificates libpcap0.8 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY app ./app

RUN useradd -r -s /usr/sbin/nologin bridge \
 && mkdir -p /data \
 && chown -R bridge:bridge /app /data

# VLC needs to create multicast sockets; the container uses host networking.
# We intentionally keep the process as root because IGMP packet capture may
# require NET_RAW in a nested LXC/Docker environment. If your setup permits
# it, change USER to bridge after testing IGMP discovery.
USER root

EXPOSE 8090

CMD ["python3", "-m", "app"]
