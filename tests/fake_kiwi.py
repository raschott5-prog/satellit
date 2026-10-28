#!/usr/bin/env python3
"""KiwiSDR-Attrappe – nur Standardbibliothek.

Spricht den von Satellit genutzten SND-Protokoll-Ausschnitt: nimmt eine
Websocket-Verbindung an, antwortet auf ``SET``-Zeilen und streamt
``SND``-Frames mit S-Meter und IMA-ADPCM-Audio. Mit ``--active`` sendet sie
einen Ton und einen hohen S-Meter-Wert (Betrieb), sonst nahe Rauschboden –
so lässt sich die Wache ohne echten Empfänger prüfen.

    python tests/fake_kiwi.py --port 18073 [--active]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from satellit.sources.kiwi import KIWI_RATE, adpcm_encode   # noqa: E402

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _accept(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()


def _send_frame(conn, payload: bytes, opcode: int = 0x2) -> None:
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    conn.sendall(bytes(header) + payload)


def _recv_handshake(conn) -> bool:
    data = b""
    conn.settimeout(5)
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(1024)
        if not chunk:
            return False
        data += chunk
    key = ""
    for line in data.decode("latin1").split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
    if not key:
        return False
    resp = ("HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {_accept(key)}\r\n\r\n")
    conn.sendall(resp.encode())
    return True


def _snd_frame(pcm_i16: np.ndarray, dbm: float, state, seq) -> bytes:
    raw = int(round((dbm + 127.0) / 0.1)) & 0x0FFF
    body = b"SND" + bytes([0]) + struct.pack("<I", seq) + struct.pack(">H", raw)
    body += adpcm_encode(pcm_i16, state)
    return body


def serve(port: int, active: bool) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    print(f"fake_kiwi auf 127.0.0.1:{port}  (active={active})")
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=_client, args=(conn, active), daemon=True).start()


def _client(conn, active: bool) -> None:
    try:
        if not _recv_handshake(conn):
            conn.close()
            return
        conn.settimeout(0.01)
        state = [0, 0]
        seq = 0
        phase = 0.0
        block = KIWI_RATE // 10          # 100-ms-Blöcke
        period = block / KIWI_RATE
        while True:
            try:
                conn.recv(4096)          # SET-Zeilen schlucken
            except socket.timeout:
                pass
            except OSError:
                break
            t = (np.arange(block) + phase) / KIWI_RATE
            phase += block
            if active:
                sig = 0.3 * np.sin(2 * np.pi * 900 * t)
                dbm = -55.0 + np.random.randn() * 4
            else:
                sig = 0.002 * np.random.randn(block)
                dbm = -108.0 + np.random.randn() * 1.5
            pcm = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
            try:
                _send_frame(conn, _snd_frame(pcm, dbm, state, seq))
            except OSError:
                break
            seq += 1
            time.sleep(period)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KiwiSDR-Attrappe für Satellit")
    ap.add_argument("--port", type=int, default=18073)
    ap.add_argument("--active", action="store_true", help="Betrieb simulieren")
    args = ap.parse_args(argv)
    try:
        serve(args.port, args.active)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
