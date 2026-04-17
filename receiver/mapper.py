#!/usr/bin/env python3
# NeoPixel library strandtest example
# Author: Tony DiCola (tony@tonydicola.com)
#
# Direct port of the Arduino NeoPixel library strandtest example.  Showcases
# various animations on a strip of NeoPixels.

import time
import asyncio
import random
import os
import json
from pathlib import Path
from rpi_ws281x import *
import argparse
import normalizer
import net_receiver

# LED strip configuration:
LED_COUNT      = 32     # Number of LED pixels.
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
#LED_PIN        = 10      # GPIO pin connected to the pixels (10 uses SPI /dev/spidev0.0).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating a signal (try 10)
ledBrightness = 75      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

# Per-pixel gain (0.0..1.0) applied multiplicatively to color for per-segment brightness
PIXEL_GAINS = [0.0] * LED_COUNT
def _ensure_gains_size(n):
    global PIXEL_GAINS
    if len(PIXEL_GAINS) != n:
        PIXEL_GAINS = [0.0] * n

ARGS_MAP_STRING = None

def parse_channel_map(map_str, ch_keys, led_count):
    """
    Parse mappings like "1:1-3,2:4-6" into { "1": (0,2), "2": (3,5) }.
    LED indices in the string are 1-based; converted to 0-based inclusive ranges.
    """
    m = {}
    if not map_str:
        return m
    parts = [p.strip() for p in map_str.split(",") if p.strip()]
    for part in parts:
        try:
            lhs, rhs = [x.strip() for x in part.split(":", 1)]
            start_s, end_s = [x.strip() for x in rhs.split("-", 1)]
            start = int(start_s) - 1
            end = int(end_s) - 1
            if start < 0 or end < start or end >= led_count:
                print(f"[map] ignoring out-of-range mapping '{part}' for led_count={led_count}")
                continue
            m[str(lhs)] = (start, end)
        except Exception as e:
            print(f"[map] ignoring malformed mapping '{part}': {e!r}")
    return m

def build_default_map(ch_keys, led_count):
    """
    Evenly splits LEDs into contiguous blocks per channel, in channel-key order.
    Example: 16 channels, 32 LEDs -> blocks of 2.
    """
    ch_keys = list(ch_keys)
    n_ch = len(ch_keys)
    if n_ch == 0:
        return {}
    block = max(1, led_count // n_ch)
    mapping = {}
    i = 0
    for k in ch_keys:
        start = i
        end = min(led_count - 1, i + block - 1)
        mapping[str(k)] = (start, end)
        i += block
        if i >= led_count:
            break
    return mapping

# Define functions which animate LEDs in various ways.
def colorWipe(strip, color, wait_ms=50):
    """Wipe color across display a pixel at a time."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(wait_ms/1000.0)

def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return Color(0, pos * 3, 255 - pos * 3)

def wheel_rgb(pos):
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)

def rainbow(strip, wait_ms=20, iterations=1):
    """Draw rainbow that fades across all pixels at once."""
    for j in range(256*iterations):
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, wheel((i+j) & 255))
        strip.show()
        time.sleep(wait_ms/1000.0)

# --- Async functions for non-blocking rendering ---
async def rainbow_async(strip, wait_ms=20):
    """Asynchronous rainbow that runs forever."""
    j = 0
    while True:
        for i in range(strip.numPixels()):
            r, g, b = wheel_rgb((i + j) & 255)
            _ensure_gains_size(strip.numPixels())
            gain = PIXEL_GAINS[i] if i < len(PIXEL_GAINS) else 0.0
            if gain < 0.0: gain = 0.0
            if gain > 1.0: gain = 1.0
            r = int(r * gain)
            g = int(g * gain)
            b = int(b * gain)
            strip.setPixelColor(i, Color(r, g, b))
        strip.show()
        j = (j + 1) & 255
        await asyncio.sleep(wait_ms / 1000.0)



# --- New brightness_from_inbox_async ---
async def brightness_from_inbox_async(strip, inbox_dir="inbox", start_index=0, sample_ms=8, poll_ms=200, delete_processed=True):
    """Continuously read EEG frames from `inbox_dir` and map first-channel amplitudes to brightness.
    - Frames are named like 0.json, 1.json, ... but indices may skip (UDP).
    - Uses normalizer.normalize_frame to map per-channel values to 0..200.
    - Applies each sample as global brightness with a short delay per sample.
    - Processed frames will be deleted when delete_processed is True.
    """
    inbox = Path(inbox_dir)
    # Resolve inbox relative to this script if a relative path was given
    if not inbox.is_absolute():
        inbox = (Path(__file__).parent / inbox).resolve()
    print(f"[inbox] monitoring {inbox} for incoming JSON frames...")
    current = start_index
    while True:
        if not inbox.exists():
            print(f"[inbox] directory does not exist yet: {inbox}")
            await asyncio.sleep(poll_ms / 1000.0)
            continue
        files = [p for p in inbox.glob("*.json") if p.stem.isdigit()]
        if files:
            indices = sorted(int(p.stem) for p in files)
            names_preview = [p.name for p in files[:10]]
            # print(f"[inbox] found {len(files)} json files in {inbox}. preview: {names_preview}")
            # print(f"[inbox] numeric indices: {indices[:20]}{'...' if len(indices) > 20 else ''}, current={current}")
            # Find the smallest index >= current
            next_idx = None
            for idx in indices:
                if idx >= current:
                    next_idx = idx
                    break
            if next_idx is None:
                max_idx = indices[-1] if indices else None
                # print(f"[inbox] no next index >= {current}; max index is {max_idx}")
                if max_idx is not None and current > max_idx:
                    # Rewind to earliest available frame so we can process existing files.
                    current = indices[0]
                    # print(f"[inbox] rewinding current to {current} to process existing frames")
                    continue
                # Nothing new yet; wait and poll again
                await asyncio.sleep(poll_ms / 1000.0)
                continue

            frame_path = inbox / f"{next_idx}.json"
            try:
                with frame_path.open("r") as f:
                    frame = json.load(f)
            except Exception as e:
                print(f"[inbox] error reading {frame_path}: {e!r}")
                await asyncio.sleep(poll_ms / 1000.0)
                # advance to avoid stalling if this index is bad
                current = next_idx + 1
                continue

            # Normalize frame using helper
            try:
                norm = normalizer.normalize_frame(frame)
            except Exception as e:
                print(f"[inbox] normalize_frame failed for {frame_path}: {e!r}; keys={list(frame.keys()) if isinstance(frame, dict) else type(frame)}")
                current = next_idx + 1
                continue

            # Pick the first channel deterministically
            ch_map = norm.get("normalized_channels", {})
            ch_keys = sorted(ch_map.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))

            map_str = ARGS_MAP_STRING
            user_map = parse_channel_map(map_str, ch_keys, strip.numPixels())
            mapping = user_map if user_map else build_default_map(ch_keys, strip.numPixels())

            num_samples = 0
            try:
                num_samples = min(len(ch_map[k]) for k in mapping.keys() if k in ch_map)
            except Exception:
                num_samples = 0
            if num_samples == 0:
                current = next_idx + 1
                continue

            for sample_idx in range(num_samples):
                for ch_key, (start, end) in mapping.items():
                    v = ch_map.get(ch_key)
                    if not v:
                        continue
                    gain = max(0.0, min(1.0, (v[sample_idx] / 50.0)))
                    for led in range(start, end + 1):
                        if 0 <= led < strip.numPixels():
                            PIXEL_GAINS[led] = gain
                await asyncio.sleep(sample_ms / 1000.0)

            print(f"[inbox] finished frame {next_idx}")

            if delete_processed:
                try:
                    frame_path.unlink()
                    # print(f"[inbox] deleted frame {frame_path.name}")
                except Exception as e:
                    print(f"[inbox] warning: could not delete {frame_path}: {e!r}")

            # Move on to the next expected index
            current = next_idx + 1
            continue

        # No files yet; wait a bit
        await asyncio.sleep(poll_ms / 1000.0)

async def run_forever(strip, args):
    render_task = asyncio.create_task(rainbow_async(strip, wait_ms=20))
    brightness_task = asyncio.create_task(
        brightness_from_inbox_async(
            strip,
            inbox_dir=getattr(args, "inbox", "inbox"),
            start_index=getattr(args, "start", 0),
            sample_ms=getattr(args, "sample_ms", 6),
            poll_ms=getattr(args, "poll_ms", 100),
            delete_processed=(not getattr(args, "keep_frames", False)),
        )
    )

    # Run blocking UDP receiver in a worker thread
    recv_task = asyncio.create_task(asyncio.to_thread(net_receiver.run))

    try:
        await asyncio.gather(render_task, brightness_task, recv_task)
    except asyncio.CancelledError:
        pass

# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    parser.add_argument('--inbox', default='inbox', help='directory where incoming frames like 0.json appear')
    parser.add_argument('--start', type=int, default=0, help='starting frame index to read')
    parser.add_argument('--sample-ms', type=int, default=4, help='delay in ms between brightness samples within a frame')
    parser.add_argument('--poll-ms', type=int, default=100, help='delay in ms when polling for new frames')
    parser.add_argument('--keep-frames', action='store_true', help='do not delete processed inbox frames (default deletes them)')
    parser.add_argument(
        '--map',
        default=(
            "1:1-2,"
            "2:3-4,"
            "3:5-6,"
            "4:7-8,"
            "5:9-10,"
            "6:11-12,"
            "7:13-14,"
            "8:15-16,"
            "9:17-18,"
            "10:19-20,"
            "11:21-22,"
            "12:23-24,"
            "13:25-26,"
            "14:27-28,"
            "15:29-30,"
            "16:31-32"
        ),
        help=(
            'channel-to-LED mapping like "1:1-3,2:4-6" '
            '(LED indices are 1-based). Defaults to 16-channel, 32-LED mapping.'
        )
    )
    args = parser.parse_args()

    ARGS_MAP_STRING = args.map

    # Create NeoPixel object with appropriate configuration.
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, ledBrightness, LED_CHANNEL)
    # Intialize the library (must be called once before other functions).
    strip.begin()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    try:
        asyncio.run(run_forever(strip, args))
    except KeyboardInterrupt:
        pass
    finally:
        net_receiver.stop()
        if args.clear:
            colorWipe(strip, Color(0,0,0), 10)
