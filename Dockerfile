FROM debian:bookworm-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv vlc ffmpeg iproute2 procps ca-certificates libpcap0.8 util-linux && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt
COPY app ./app
RUN useradd -r -s /usr/sbin/nologin bridge && mkdir -p /data/hls && chown -R bridge:bridge /app /data
USER root
EXPOSE 8090
CMD ["python3", "-m", "app"]
