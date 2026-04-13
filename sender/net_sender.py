import os, socket, struct, time
from typing import Optional

HOST = os.getenv("EEG_UDP_HOST", "10.201.73.92")   # change later to other Pi's IP
PORT = int(os.getenv("EEG_UDP_PORT", "50008"))
CHUNK = 1200                                    # keep < MTU to avoid fragmentation issues
MAGIC = b"EEG0"                                 # 4 bytes
VERSION = 1

# Header format (network byte order):
#   4s   B     I         H            H            H
#  MAGIC VER frame_id total_chunks chunk_index payload_len
HDR = struct.Struct("!4sB I H H H")

def _frame_id_from_filename(path: str) -> int:
    # try to parse "123.json" -> 123; else use time-based id
    base = os.path.basename(path)
    stem = base.split(".")[0]
    try:
        return int(stem)
    except ValueError:
        return int(time.time() * 1000) & 0xFFFFFFFF

def send(filepath: str, frame_id: Optional[int] = None) -> bool:
    """
    Fire-and-forget UDP send of one JSON file, chunked with sequence numbers.
    Returns True if datagrams were queued to the OS without exceptions.
    """
    if not os.path.isfile(filepath):
        print(f"[udp] no such file: {filepath}")
        return False

    data = open(filepath, "rb").read()
    fid = _frame_id_from_filename(filepath) if frame_id is None else (frame_id & 0xFFFFFFFF)

    # split into CHUNK-sized pieces
    parts = [data[i:i+CHUNK] for i in range(0, len(data), CHUNK)]
    total = len(parts) if parts else 1
    if not parts:
        parts = [b""]

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((HOST, PORT))  # sets default peer; UDP doesn't "connect" in the TCP sense
            for idx, payload in enumerate(parts):
                hdr = HDR.pack(MAGIC, VERSION, fid, total, idx, len(payload))
                sock.sendall(hdr + payload)
        return True
    except Exception as e:
        print(f"[udp] send error: {e}")
        return False
