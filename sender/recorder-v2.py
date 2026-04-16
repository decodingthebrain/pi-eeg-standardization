import spidev
import time
from RPi import GPIO
from scipy import signal
import threading
import asyncio
import queue
import os
import json
import net_sender
from datetime import datetime, timezone

FRAMES_DIR = "frames"
os.makedirs(FRAMES_DIR, exist_ok=True)

button_pin_1 =  26 #13
button_pin_2 =  13
cs_pin = 19

# Config Global Constants
CHANNELS = 16
SAMPLE_LEN = 160
FPS = 250
HISTORY = 250  # number of past samples to give the filters context (~1 s at 250 Hz)
HIGHCUT = 1
LOWCUT = 10

FRAMES_DIR = "frames"
os.makedirs(FRAMES_DIR, exist_ok=True)


class EEGRecorder:
    def __init__(self, loop):
        # 1. Hardware Setup (RPi.GPIO, spidev)
        self.loop = loop
        self.cs_pin = 19
        self.frame_idx = 0

        # 2D list containing 16 empty lists for each data channel
        self.channels = [[] for _ in range(16)]
        self.prev = [[0.0] * HISTORY for _ in range(16)]

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(cs_pin, GPIO.OUT)
        GPIO.output(cs_pin, GPIO.HIGH)

        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 75_000
        self.spi.lsbfirst = False
        self.spi.mode = 0b01
        self.spi.bits_per_word = 8

        self.spi_2 = spidev.SpiDev()
        self.spi_2.open(0, 1)
        self.spi_2.max_speed_hz = 75_000
        self.spi_2.lsbfirst = False
        self.spi_2.mode = 0b01
        self.spi_2.bits_per_word = 8
        
        # 2. Communication Bridges
        # Raw samples go from Thread -> Async Queue
        self.data_queue = asyncio.Queue(maxsize=100)
        self.stop_event = threading.Event()


    def write_byte(self, target_spi, addr, value):
        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.LOW)

        target_spi.xfer2([addr | 0x40, 0x00, value])

        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.HIGH)

    def send_command(self, target_spi, cmd):
        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.LOW)

        target_spi.xfer2([cmd])

        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.HIGH)

    def read_byte(self, target_spi, addr):
        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.LOW)

        response = target_spi.xfer2([addr | 0x20, 0x00]) 

        if (target_spi == self.spi_2):
            GPIO.output(self.cs_pin, GPIO.HIGH)
        return response[1]

    def producer_thread(self):
        print("[Thread] Starting SPI Acquisition...")

        who_i_am=0x00
        config1=0x96
        config2=0XD0
        config3=0X03
        ch1set=0x05
        ch2set=0x06
        ch3set=0x07
        ch4set=0x08
        ch5set=0x09
        ch6set=0x0A
        ch7set=0x0B
        ch8set=0x0C

        wakeup=0x02
        reset=0x06
        stop=0x0A
        start=0x08
        sdatac=0x11
        rdatac=0x10
        rdata = 0x12

        for targetSpi in [self.spi, self.spi_2]:
            # Initialize Chip
            self.send_command (targetSpi, sdatac)
            self.send_command (targetSpi, reset)
            self.send_command (targetSpi, start)
            self.send_command (targetSpi, rdatac)

            # Config
            self.write_byte (targetSpi, 0x14, 0x80) #GPIO 80
            self.write_byte (targetSpi, config1, 0x96)
            self.write_byte (targetSpi, config2, 0xD4)
            self.write_byte (targetSpi, config3, 0xFF)
            self.write_byte (targetSpi, 0x04, 0x00)
            self.write_byte (targetSpi, 0x0D, 0x00)
            self.write_byte (targetSpi, 0x0E, 0x00)
            self.write_byte (targetSpi, 0x0F, 0x00)
            self.write_byte (targetSpi, 0x10, 0x00)
            self.write_byte (targetSpi, 0x11, 0x00)
            self.write_byte (targetSpi, 0x15, 0x20)

            self.write_byte (targetSpi, 0x17, 0x00)
            self.write_byte (targetSpi, ch1set, 0x00)
            self.write_byte (targetSpi, ch2set, 0x00)
            self.write_byte (targetSpi, ch3set, 0x00)
            self.write_byte (targetSpi, ch4set, 0x00)
            self.write_byte (targetSpi, ch5set, 0x00)
            self.write_byte (targetSpi, ch6set, 0x00)
            self.write_byte (targetSpi, ch7set, 0x01)
            self.write_byte (targetSpi, ch8set, 0x01)

            self.send_command (targetSpi, rdatac)
            self.send_command (targetSpi, start)
        

        print("[Thread] Shield Initialized. Starting Acquisition.")

        while not self.stop_event.is_set():
            header1 = self.spi.readbytes(1)[0]

            if header1 == 192:
                remaining1 = self.spi.readbytes(26)
                output = [header1] + remaining1

                GPIO.output(self.cs_pin, GPIO.LOW)
                output_2 = self.spi_2.readbytes(27)
                GPIO.output(self.cs_pin, GPIO.HIGH)

                if output_2[0] == 192:
                    payload = {
                        "out1": output,
                        "out2": output_2,
                        "ts": datetime.now(timezone.utc).isoformat()
                    }
                    self.loop.call_soon_threadsafe(self.data_queue.put_nowait, payload)
                else:
                    print(f"Chip 2 Misalign: {output_2[0]}")
            else:
                pass

        
    async def network_consumer(self):
        while True:
            sample = await self.data_queue.get()

            for a in range (8):
                start = 3 + (a * 3)
                raw_int = _to_signed_24bit(sample["out1"][start],sample["out1"][start+1],sample["out1"][start+2])
                voltage_uv = (raw_int * 4.5) / (8388607.0 * 24) * 1000000
                self.channels[a].append(round(voltage_uv, 2))
            
            for a in range (8):
                start = 3 + (a * 3)
                raw_int_2 = _to_signed_24bit(sample["out2"][start],sample["out2"][start+1],sample["out2"][start+2])
                voltage_uv2 = (raw_int_2 * 4.5) / (8388607.0 * 24) * 1000000
                self.channels[a+8].append(round(voltage_uv2, 2))

            if len(self.channels[0]) >= SAMPLE_LEN:
                # Build filtered windows for each channel using rolling history (prev)
                current_chunks = [list(ch) for ch in self.channels]
                # Reset lists for next batch
                self.channels = [[] for _ in range(16)]
    
                # Start filtering
                filtered_windows = []
                for i, chunk in enumerate(current_chunks):
                        combined = self.prev[i] + chunk
                        # Band‑pass: high‑pass then low‑pass (both zero‑phase)
                        hp = butter_highpass_filter(combined, HIGHCUT, FPS)
                        bp = butter_lowpass_filter(hp, LOWCUT, FPS)
                        win = bp[-SAMPLE_LEN:]  # keep only newest 160 samples
                        filtered_windows.append(list(map(float, win)))
                        self.prev[i] = combined[-HISTORY:]  # update history
    
                (win_1, win_2, win_3, win_4, win_5, win_6, win_7, win_8,
                    win_9, win_10, win_11, win_12, win_13, win_14, win_15, win_16) = filtered_windows
                
                display_values = {}
                for i, win in enumerate(filtered_windows):
                    # Get Absolute values (remove negatives)
                    abs_values = [abs(x) for x in win]

                    # Calculate the average strength of the signal in this window
                    strength = sum(abs_values) / len(abs_values)

                    # Store values for the LED mapper
                    display_values[str(i+1)] = round(strength, 2)
            
                    
                frame = {
                    "ts": datetime.now(timezone.utc).isoformat() + "Z",
                    "fs": FPS,
                    "frame_index": self.frame_idx,
                    "channels": display_values,
                    "raw_windows": filtered_windows
                }

                out_path = os.path.join(FRAMES_DIR, f"{self.frame_idx}.json")

                with open(out_path, "w") as f:
                    json.dump(frame, f)
                
                await self.loop.run_in_executor(None, net_sender.send, out_path)

                if os.path.exists(out_path):
                    os.remove(out_path)

                self.frame_idx += 1
            
            self.data_queue.task_done()

# Helper filter and voltage conversion functions
def butter_lowpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = signal.butter(order, normal_cutoff, btype='low', analog=False)
    return b, a
def butter_lowpass_filter(data, cutoff, fs, order=5):
    b, a = butter_lowpass(cutoff, fs, order=order)
    y = signal.filtfilt(b, a, data)
    return y
def butter_highpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = signal.butter(order, normal_cutoff, btype='high', analog=False)
    return b, a
def butter_highpass_filter(data, cutoff, fs, order=5):
    b, a = butter_highpass(cutoff, fs, order=order)
    y = signal.filtfilt(b, a, data)
    return y

def _to_signed_24bit(msb: int, middle: int, lsb: int) -> int:
    # Combine the bytes into a 24-bit integer
    combined = (msb << 16) | (middle << 8) | lsb

    # Check the sign bit (bit 7 of the MSB)
    if (msb & 0x80) != 0:
        # Convert to negative 24-bit signed integer
        combined -= 1 << 24

    return combined

# Main
async def main():
    loop = asyncio.get_running_loop()
    recorder = EEGRecorder(loop)

    thread = threading.Thread(target=recorder.producer_thread, daemon=True)
    thread.start()

    try:
        await recorder.network_consumer()
    except asyncio.CancelledError:
        recorder.stop_event.set()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        GPIO.cleanup()