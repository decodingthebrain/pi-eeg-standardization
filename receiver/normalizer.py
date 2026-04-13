import json
import numpy as np
import os
import time

def normalize_channel(values):
    # Normalize one channel to range (0, 200) relative to zero amplitude.
    arr = np.array(values, dtype=np.float64)
    abs_arr = np.abs(arr)
    max_val = abs_arr.max()
    if max_val == 0:
        return np.zeros_like(abs_arr).tolist()
    normalized = (abs_arr / max_val) * 200
    return normalized.tolist()

def normalize_frame(frame_data):
    #Normalize all channels in one EEG frame.
    normalized_channels = {}
    for ch_id, values in frame_data["channels"].items():
        normalized_channels[ch_id] = normalize_channel(values)
    return {
        "ts": frame_data["ts"],
        "fs": frame_data["fs"],
        "frame_idx": frame_data["frame_index"],
        "normalized_channels": normalized_channels
    }

# normalize using 'normal = normalize_frame(data)'
# ex. first_channel = normal['normalized_channels']['1']
