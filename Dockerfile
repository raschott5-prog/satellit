# Satellit im Container (Linux, amd64 und arm64/Raspberry Pi)
#
#   docker compose up -d --build        # siehe compose.yaml und docs/docker.md
#
# Ton: Der Container spielt über den PulseAudio-/PipeWire-Socket des Rechners
# (PortAudio → ALSA → Pulse-Plugin). Unter Docker Desktop (Windows/macOS) gibt es
# diesen Socket nicht – dort bitte die Beta-Pakete nehmen.
#
# Funk-Teil: --build-arg FUNK=1 installiert KiwiSDR/UberSDR (websocket-client,
# opuslib). Übersetzer (faster-whisper, groß) mit --build-arg UEBERSETZER=1.
# Die WebSDR-Quelle (Chromium) ist im Container nicht vorgesehen.
#
# Schlank gehalten: Das Debian-ffmpeg und das ALSA-Plugin-Paket ziehen zusammen
# ~450 MB Bibliotheken (Grafik, Vulkan, X11, libavcodec) nach. Stattdessen ein
# eigenes, reines Audio-ffmpeg (wenige MB) und aus libasound2-plugins nur die
# beiden Pulse-Module.

# --- ffmpeg nur für Audio: Streams (HTTP/HTTPS/HLS) und Dateien → PCM -------
FROM docker.io/library/python:3.12-slim AS ffmpeg
ARG FFMPEG_VERSION=8.1.2
# Prüfsumme des offiziellen Tarballs (Signatur des FFmpeg-Release-Schlüssels
# FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8 am 13.11.2026 geprüft)
ARG FFMPEG_SHA256=464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config libssl-dev curl xz-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
 && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
 && tar xf ffmpeg.tar.xz --strip-components=1 \
 && ./configure --prefix=/opt/ffmpeg \
      --disable-everything --disable-doc --disable-debug --disable-autodetect \
      --disable-ffplay --disable-ffprobe --disable-avdevice --disable-swscale \
      --disable-x86asm --enable-openssl --enable-version3 \
      --enable-protocol=file,pipe,http,https,tcp,udp,tls,hls,crypto,httpproxy \
      --enable-demuxer=mp3,aac,ogg,flac,wav,mov,mpegts,hls,matroska,w64,aiff,loas \
      --enable-decoder=mp3,mp3float,mp2,mp2float,aac,aac_latm,vorbis,opus,flac,alac,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_u8 \
      --enable-parser=mpegaudio,aac,aac_latm,vorbis,opus,flac \
      --enable-encoder=pcm_f32le --enable-muxer=pcm_f32le \
      --enable-filter=aresample,aformat,anull,abuffer,abuffersink,null,format,buffer,buffersink \
 && make -j"$(nproc)" && make install && strip /opt/ffmpeg/bin/ffmpeg

# --- nur die Pulse-Module des ALSA-Plugin-Pakets -----------------------------
FROM docker.io/library/python:3.12-slim AS alsa-pulse
RUN apt-get update \
 && cd /tmp && apt-get download libasound2-plugins \
 && dpkg-deb -x libasound2-plugins_*.deb /tmp/x \
 && mkdir /out \
 && cp "$(find /tmp/x -name libasound_module_pcm_pulse.so)" \
       "$(find /tmp/x -name libasound_module_ctl_pulse.so)" /out/

# --- Satellit -----------------------------------------------------------------
FROM docker.io/library/python:3.12-slim

ARG FUNK=0
ARG UEBERSETZER=0

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libportaudio2 libpulse0 tzdata \
      $( [ "$FUNK" = "1" ] && echo libopus0 ) \
 && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /usr/local/bin/ffmpeg
# Pulse-Module dorthin, wo libasound2 sie sucht (je nach Architektur)
COPY --from=alsa-pulse /out/ /tmp/alsa-pulse/
RUN d="$(dirname "$(find /usr/lib -name libasound.so.2 | head -1)")/alsa-lib" \
 && mkdir -p "$d" && mv /tmp/alsa-pulse/*.so "$d/" && rmdir /tmp/alsa-pulse
# ALSA-Standardgerät = Pulse-Socket des Rechners
COPY docker/asound.conf /etc/asound.conf

WORKDIR /app
RUN pip install --no-cache-dir "numpy>=1.23" "requests>=2.28" "sounddevice>=0.4" \
 && if [ "$FUNK" = "1" ]; then pip install --no-cache-dir "websocket-client>=1.5" "opuslib>=3.0"; fi \
 && if [ "$UEBERSETZER" = "1" ]; then pip install --no-cache-dir "faster-whisper>=1.0"; fi

COPY satellit/ satellit/
COPY static/ static/
COPY beispiele/ beispiele/
COPY LICENSE README.md ./

# Konfiguration, Medien und Chronik liegen im Volume /config
# (→ /config/satellit/config.json, wie ~/.config/satellit außerhalb).
# Läuft als UID 1000, damit der Pulse-Socket des Rechners zugänglich ist.
RUN useradd -u 1000 -m satellit && mkdir -p /config && chown satellit /config
USER satellit
ENV XDG_CONFIG_HOME=/config \
    PULSE_SERVER=unix:/run/pulse/native \
    TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1

EXPOSE 8080
VOLUME ["/config"]
# Im Container muss die Oberfläche auf allen Adressen lauschen; wer sie von
# außen erreicht, regelt die Port-Freigabe in compose.yaml.
CMD ["python", "-m", "satellit", "--listen", "0.0.0.0"]
