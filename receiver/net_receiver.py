import os
import sys
import time
import json
import socket
import struct
import threading
from collections import defaultdict, deque
from typing import Dict, Tuple

HOST = os.getenv("EEG_UDP_HOST", '') # listen on all interfaces by default
PORT = int(os.getenv("EEG_UDP_PORT", "50008"))
OUT_DIR = os.getenv("EEG_OUT_DIR", "inbox")
FRAME_TIMEOUT_S = float(os.getenv("EEG_FRAME_TIMEOUT_S", "2.0"))  # drop if incomplete after N seconds
MAX_OPEN_FRAMES = int(os.getenv("EEG_MAX_OPEN_FRAMES", "256"))    # guardrail

stop_event = threading.Event()

MAGIC = b"EEG0"
VERSION = 1
HDR = struct.Struct("!4sB I H H H")  # MAGIC, VER, frame_id, total_chunks, chunk_index, payload_len

os.makedirs(OUT_DIR, exist_ok=True)

class FrameBuffer:
    __slots__ = ("arrival_ts", "total", "parts", "received")
    def __init__(self, total: int):
        self.arrival_ts = time.time()
        self.total = total
        self.parts: Dict[int, bytes] = {}
        self.received = 0

    def add(self, idx: int, payload: bytes) -> None:
        if idx not in self.parts:
            self.parts[idx] = payload
            self.received += 1
        # duplicates silently ignored

    def complete(self) -> bool:
        return self.received == self.total and self.total == (max(self.parts.keys()) + 1 if self.parts else 0)

    def assemble(self) -> bytes:
        return b"".join(self.parts[i] for i in range(self.total))

def save_json_bytes(frame_id: int, buf: bytes) -> Tuple[bool, str]:
    """Validate JSON and write to OUT_DIR. Returns (ok, path)."""
    # Basic corruption check: JSON must parse, and be a dict with channels.
    try:
        obj = json.loads(buf.decode("utf-8"))
    except Exception as e:
        print(f"[recv] frame {frame_id}: invalid JSON ({e}); corrupted frame deleted")
        return False, ""

    # Optional sanity checks
    ok = isinstance(obj, dict) and "channels" in obj and isinstance(obj["channels"], dict)
    path = os.path.join(OUT_DIR, f"{frame_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    if not ok:
        os.remove(path)
        print(f"[recv] frame {frame_id}: JSON parsed but failed schema check; deleted {path}")
        return False, ""
    print(f"I received {frame_id}.json and wrote to {path}")
    return True, path

def run():
    frames: Dict[int, FrameBuffer] = {}
    order = deque()  # track arrival order for eviction

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)

        try:
            # Broadcast is often needed for the .255 address
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Only try this if running with sudo
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b'wlan0')
            except:
                pass 
            
            sock.bind((HOST, PORT))
        except PermissionError:
            print(f"Permission Error: Use sudo to bind to {PORT}")
            return

        # short timeout ensures loop checks stop_event regularly
        sock.settimeout(0.25)  # periodic wake-ups for GC

        print(f"[recv] listening on {HOST}:{PORT}, writing complete frames to {OUT_DIR}/", flush=True)


        while not stop_event.is_set():
            # Garbage-collect stale frames
            now = time.time()
            while order and now - frames[order[0]].arrival_ts > FRAME_TIMEOUT_S:
                fid = order.popleft()
                fb = frames.pop(fid, None)
                if fb:
                    print(f"[recv] drop frame {fid}: timeout after {FRAME_TIMEOUT_S}s ({fb.received}/{fb.total} chunks)")

            # Bound number of open frames
            if len(frames) > MAX_OPEN_FRAMES and order:
                fid = order.popleft()
                fb = frames.pop(fid, None)
                if fb:
                    print(f"[recv] drop frame {fid}: evicted (open>{MAX_OPEN_FRAMES})")

            try:
                pkt, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                print("\n[recv] shutdown")
                stop_event.set()
                break

            if len(pkt) < HDR.size:
                print("[recv] short packet ignored")
                continue

            try:
                magic, ver, frame_id, total, idx, plen = HDR.unpack_from(pkt, 0)
            except struct.error:
                print("[recv] header unpack error; packet ignored")
                continue

            if magic != MAGIC or ver != VERSION:
                print(f"[recv] bad magic/version from {addr}; got {magic!r}/{ver}, expected {MAGIC!r}/{VERSION}")
                continue

            payload = pkt[HDR.size:]
            if len(payload) != plen:
                print(f"[recv] len mismatch: hdr {plen} vs actual {len(payload)}; dropping chunk")
                continue

            if total == 0 or idx >= total:
                print(f"[recv] bad indices: total={total}, idx={idx}")
                continue

            # Get or create buffer
            fb = frames.get(frame_id)
            if fb is None:
                fb = FrameBuffer(total)
                frames[frame_id] = fb
                order.append(frame_id)
            else:
                # total must be consistent
                if fb.total != total:
                    print(f"[recv] conflicting totals for frame {frame_id}: {fb.total} vs {total}; dropping frame")
                    # drop entire frame
                    frames.pop(frame_id, None)
                    try:
                        order.remove(frame_id)
                    except ValueError:
                        pass
                    continue

            fb.add(idx, payload)

            if fb.complete():
                # Assemble and write
                buf = fb.assemble()
                save_json_bytes(frame_id, buf)
                # cleanup
                frames.pop(frame_id, None)
                try:
                    order.remove(frame_id)
                except ValueError:
                    pass

def stop():
    """Signal the receiver loop to stop gracefully."""
    stop_event.set()

if __name__ == "__main__":
    print("Script started! Attempting to listen...", flush=True)
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopping receiver...")
        stop()
    except Exception as e:
        print(f"Fatal Error: {e}")
