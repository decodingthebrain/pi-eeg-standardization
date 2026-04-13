import spidev
import time
from RPi import GPIO
from matplotlib import pyplot as plt
from scipy.ndimage import gaussian_filter1d
from scipy import signal
#import gpiod
#from importlib.metadata import version
import net_sender
import os
import json
from datetime import datetime, timezone

FRAMES_DIR = "frames"
os.makedirs(FRAMES_DIR, exist_ok=True)
frame_idx = 0

#GPIO.setwarnings(False) 
#GPIO.setmode(GPIO.BOARD)

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

button_pin_1 =  26 #13
button_pin_2 =  13
cs_pin = 19
#chip = gpiod.Chip("gpiochip4")
#print(version("gpiod"))
#chip = gpiod.chip("0")
#chip = gpiod.chip("0")
#cs_line = chip.get_line(19)  # GPIO19
#cs_line.request(consumer="SPI_CS", type=gpiod.LINE_REQ_DIR_OUT)
#cs_line = chip.get_line(cs_pin)
#cs_line_out = gpiod.line_request()
#cs_line_out.consumer = "SPI_CS"
#cs_line_out.request_type = gpiod.line_request.DIRECTION_OUTPUT
#cs_line.request(cs_line_out)

GPIO.setup(cs_pin, GPIO.OUT)
GPIO.output(cs_pin, GPIO.HIGH)

#cs_line.request(consumer="SPI_CS", type=gpiod.line_request.DIRECTION_OUTPUT)
#cs_line.set_value(1)  # Set CS high initially

spi = spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz  = 75_000
spi.lsbfirst=False
spi.mode=0b01
spi.bits_per_word = 8

spi_2 = spidev.SpiDev()
spi_2.open(0,1)
spi_2.max_speed_hz= 75_000
spi_2.lsbfirst=False
spi_2.mode=0b01
spi_2.bits_per_word = 8

who_i_am=0x00
config1=0x01
config2=0X02
config3=0X03

reset=0x06
stop=0x0A
start=0x08
sdatac=0x11
rdatac=0x10
wakeup=0x02
rdata = 0x12

ch1set=0x05
ch2set=0x06
ch3set=0x07
ch4set=0x08
ch5set=0x09
ch6set=0x0A
ch7set=0x0B
ch8set=0x0C

data_test= 0x7FFFFF
data_check=0xFFFFFF

def read_byte(register):
 write=0x20
 register_write=write|register
 data = [register_write,0x00,register]
 read_reg=spi.xfer(data)
 print ("data", read_reg)
 
def send_command(command):
 send_data = [command]
 com_reg=spi.xfer(send_data)
 
def write_byte(register,data):
 write=0x40
 register_write=write|register
 data = [register_write,0x00,data]
 print (data)
 spi.xfer(data)

def read_byte_2(register):
 write=0x20
 register_write=write|register
 data = [register_write,0x00,register]
 #cs_line.set_value(0)
 GPIO.output(cs_pin, GPIO.LOW)
 read_reg=spi.xfer(data)
 #cs_line.set_value(1)
 GPIO.output(cs_pin. GPIO.HIGH)
 print ("data", read_reg)
 
def send_command_2(command):
 send_data = [command]
 #cs_line.set_value(0)
 GPIO.output(cs_pin, GPIO.LOW)
 spi_2.xfer(send_data)
 #cs_line.set_value(1)
 GPIO.output(cs_pin. GPIO.HIGH)
 
def write_byte_2(register,data):
 write=0x40
 register_write=write|register
 data = [register_write,0x00,data]
 print (data)

 #cs_line.set_value(0)
 GPIO.output(cs_pin, GPIO.LOW)
 spi_2.xfer(data)
 #cs_line.set_value(1)
 GPIO.output(cs_pin. GPIO.HIGH)

 

send_command (wakeup)
send_command (stop)
send_command (reset)
send_command (sdatac)

write_byte (0x14, 0x80) #GPIO 80
write_byte (config1, 0x96)
write_byte (config2, 0xD4)
write_byte (config3, 0xFF)
write_byte (0x04, 0x00)
write_byte (0x0D, 0x00)
write_byte (0x0E, 0x00)
write_byte (0x0F, 0x00)
write_byte (0x10, 0x00)
write_byte (0x11, 0x00)
write_byte (0x15, 0x20)
#
write_byte (0x17, 0x00)
write_byte (ch1set, 0x00)
write_byte (ch2set, 0x00)
write_byte (ch3set, 0x00)
write_byte (ch4set, 0x00)
write_byte (ch5set, 0x00)
write_byte (ch6set, 0x00)
write_byte (ch7set, 0x01)
write_byte (ch8set, 0x01)

send_command (rdatac)
send_command (start)


send_command_2 (wakeup)
send_command_2 (stop)
send_command_2 (reset)
send_command_2 (sdatac)

write_byte_2 (0x14, 0x80) #GPIO 80
write_byte_2 (config1, 0x96)
write_byte_2 (config2, 0xD4)
write_byte_2 (config3, 0xFF)
write_byte_2 (0x04, 0x00)
write_byte_2 (0x0D, 0x00)
write_byte_2 (0x0E, 0x00)
write_byte_2 (0x0F, 0x00)
write_byte_2 (0x10, 0x00)
write_byte_2 (0x11, 0x00)
write_byte_2 (0x15, 0x20)
#
write_byte_2 (0x17, 0x00)
write_byte_2 (ch1set, 0x00)
write_byte_2 (ch2set, 0x00)
write_byte_2 (ch3set, 0x00)
write_byte_2 (ch4set, 0x00)
write_byte_2 (ch5set, 0x00)
write_byte_2 (ch6set, 0x00)
write_byte_2 (ch7set, 0x01)
write_byte_2 (ch8set, 0x01)

send_command_2 (rdatac)
send_command_2 (start)

DRDY=1

result=[0]*27
result_2=[0]*27


data_1ch_test = []
data_2ch_test = []
data_3ch_test = []
data_4ch_test = []
data_5ch_test = []
data_6ch_test = []
data_7ch_test = []
data_8ch_test = []

data_9ch_test = []
data_10ch_test = []
data_11ch_test = []
data_12ch_test = []
data_13ch_test = []
data_14ch_test = []
data_15ch_test = []
data_16ch_test = []

# sample length (data points)
sample_len = 100

#1.2 Band-pass filter
data_before = []
data_after =  []

just_one_time = 0
data_lenght_for_Filter = 2     # how much we read data for filter, all lenght  [_____] + [_____] + [_____]
read_data_lenght_one_time = 1   # for one time how much read  [_____]

sample_len = 100   # save 100 samples per channel per frame
sample_lens = 100
fps = 250
highcut = 1
lowcut = 10

HISTORY = 250  # number of past samples to give the filters context (~1 s at 250 Hz)
prev = [[0.0] * HISTORY for _ in range(16)]  # rolling history per channel

print (data_lenght_for_Filter*read_data_lenght_one_time-read_data_lenght_one_time)

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

last_valid_value = 5
counter = 0

def _to_signed_24bit(msb: int, middle: int, lsb: int) -> int:
    # Combine the bytes into a 24-bit integer
    combined = (msb << 16) | (middle << 8) | lsb

    # Check the sign bit (bit 7 of the MSB)
    if (msb & 0x80) != 0:
        # Convert to negative 24-bit signed integer
        combined -= 1 

    return combined

while 1:
        # read ADC1
        #cs_line.set_value(1)
        GPIO.output(cs_pin. GPIO.HIGH)
        output=spi.readbytes(27)
        # read ADC2
        #cs_line.set_value(0)
        GPIO.output(cs_pin, GPIO.LOW)
        output_2=spi_2.readbytes(27)
        #cs_line.set_value(1)
        GPIO.output(cs_pin. GPIO.HIGH)
        
        #hdr1_ok = (len(output) == 27 and output[0] == 0xC0 and output[1] == 0x00 and output[2] == 0x08)
        #hdr2_ok = (len(output_2) == 27 and output_2[0] == 0xC0 and output_2[1] == 0x00 and output_2[2] == 0x08)
        #if not (hdr1_ok and hdr2_ok): 
                #frame_idx += 1
                #continue
        
        #print("H1:", output)
        #print("H2:", output_2)
        #print (output[0],output[1],output[2])

        if output_2[0]==192 and output_2[1] == 0 and output_2[2] == 8:
            #print ("ok4")
            for a in range (8):
                start = 3 + (a * 3)
                raw_int = _to_signed_24bit(output[start], output[start+1], output[start+2])
                voltage_uv = (raw_int * 4.5) / (8388607.0 * 24) * 1000000
                result[a] = round(voltage_uv, 2)
                # change range to 3,25,3
                #voltage_1=(output[a]<<8)| output[a+1]
                #voltage_1=(voltage_1<<8)| output[a+2]
                #convert_voktage=voltage_1|data_test
                #if convert_voktage==data_check:
                    #voltage_1_after_convert=(voltage_1-16777214)
                #else:
                    #voltage_1_after_convert=voltage_1
                #channel_num =  (a/3)

                #result[int (channel_num)]=round(1000000*4.5*(voltage_1_after_convert/16777215),2)

            data_1ch_test.append(result[1])
            data_2ch_test.append(result[2])
            data_3ch_test.append(result[3])
            data_4ch_test.append(result[4])
            data_5ch_test.append(result[5])
            data_6ch_test.append(result[6])
            data_7ch_test.append(result[7])
            data_8ch_test.append(result[8])


            for a in range (8):
                start = 3 + (a * 3)
                raw_int_2 = _to_signed_24bit(output_2[start], output_2[start+1], output_2[start+2])
                voltage_uv_2 = (raw_int_2 * 4.5) / (8388607.0 * 24) * 1000000
                result_2[a+1] = round(voltage_uv_2, 2)
                #voltage_1=(output_2[a]<<8)| output_2[a+1]
                #voltage_1=(voltage_1<<8)| output_2[a+2]
                #convert_voktage=voltage_1|data_test
                #if convert_voktage==data_check:
                    #voltage_1_after_convert=(voltage_1-16777214)
                #else:
                    #voltage_1_after_convert=voltage_1
                #channel_num =  (a/3)

                #result_2[int (channel_num)]=round(1000000*4.5*(voltage_1_after_convert/16777215),2)

            data_9ch_test.append(result_2[1])
            data_10ch_test.append(result_2[2])
            data_11ch_test.append(result_2[3])
            data_12ch_test.append(result_2[4])
            data_13ch_test.append(result_2[5])
            data_14ch_test.append(result_2[6])
            data_15ch_test.append(result_2[7])
            data_16ch_test.append(result_2[8])


            if len(data_9ch_test)==sample_len:

                # Build filtered windows for each channel using rolling history (prev)
                current_chunks = [
                        list(map(float, data_1ch_test)),
                        list(map(float, data_2ch_test)),
                        list(map(float, data_3ch_test)),
                        list(map(float, data_4ch_test)),
                        list(map(float, data_5ch_test)),
                        list(map(float, data_6ch_test)),
                        list(map(float, data_7ch_test)),
                        list(map(float, data_8ch_test)),
                        list(map(float, data_9ch_test)),
                        list(map(float, data_10ch_test)),
                        list(map(float, data_11ch_test)),
                        list(map(float, data_12ch_test)),
                        list(map(float, data_13ch_test)),
                        list(map(float, data_14ch_test)),
                        list(map(float, data_15ch_test)),
                        list(map(float, data_16ch_test)),
                ]

                filtered_windows = []
                for i, chunk in enumerate(current_chunks):
                        combined = prev[i] + chunk
                        # Band‑pass: high‑pass then low‑pass (both zero‑phase)
                        hp = butter_highpass_filter(combined, highcut, fps)
                        bp = butter_lowpass_filter(hp, lowcut, fps)
                        win = bp[-sample_len:]  # keep only newest 100 samples
                        filtered_windows.append(list(map(float, win)))
                        prev[i] = combined[-HISTORY:]  # update history

                (win_1, win_2, win_3, win_4, win_5, win_6, win_7, win_8,
                    win_9, win_10, win_11, win_12, win_13, win_14, win_15, win_16) = filtered_windows
                
                frame = {
                    "ts": datetime.now(timezone.utc).isoformat() + "Z",
                    "fs": fps,
                    "frame_index": frame_idx,
                    "channels": {
                    "1": win_1,
                    "2": win_2,
                    "3": win_3,
                    "4": win_4,
                    "5": win_5,
                    "6": win_6,
                    "7": win_7,
                    "8": win_8,
                    "9": win_9,
                    "10": win_10,
                    "11": win_11,
                    "12": win_12,
                    "13": win_13,
                    "14": win_14,
                    "15": win_15,
                    "16": win_16
                    },
                }
                
                out_path = os.path.join(FRAMES_DIR, f"{frame_idx}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(frame, f, ensure_ascii=False)
                        
                print(f"I wrote {frame_idx}.json")
                print(f"I'm sending {frame_idx}.json...")
                net_sender.send(out_path)
                os.remove(out_path)
                        
                frame_idx += 1
                
                # cleanup
                data_1ch_test = []
                data_2ch_test = []
                data_3ch_test = []
                data_4ch_test = []
                data_5ch_test = []
                data_6ch_test = []
                data_7ch_test = []
                data_8ch_test = []
                data_9ch_test = []
                data_10ch_test = []
                data_11ch_test = []
                data_12ch_test = []
                data_13ch_test = []
                data_14ch_test = []
                data_15ch_test = []
                data_16ch_test = []
            
            else:
                pass

                                
           
