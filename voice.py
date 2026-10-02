import os
import torch
import numpy as np
import scipy.io.wavfile as wavfile
from bark import SAMPLE_RATE, generate_audio, preload_models

# CPU mode force karna GitHub Actions ke liye taaki crash na ho
os.environ["SUNO_OFFLOAD_CPU"] = "True"
os.environ["SUNO_USE_SMALL_MODELS"] = "True"

print("[*] Loading Bark AI Models...")
preload_models()

# 1 Minute ke Call of Duty aggressive dialogue chunks (tags ke sath)
cod_chunks = [
    "[shouts] GO GO GO! Move up! They are planting the bomb at B site! What are you doing?! Shoot them!",
    "[angry] Reloading! Cover me! Sniper on the left roof, watch out! Watch out!",
    "[screaming] CONTACT! Multiple hostiles incoming! Light them up with everything we got! Fire!",
    "[shouts] Grenade out! Get down! Boom! That's what you get!",
    "[angry] Push forward, do not let them breathe! Clear the building, room by room!",
    "[shouts] Mission success! That is how we do it in Task Force 141! Absolute domination!"
]

temp_wavs = []

print("[*] Generating emotional voice chunks via Bark...")
for i, text in enumerate(cod_chunks):
    print(f"Generating chunk {i+1}/6...")
    # Bark AI ke zariye audio array generate karna
    audio_array = generate_audio(text, history_prompt="v2/en_speaker_6") # Deep aggressive voice profile
    
    filename = f"chunk_{i}.wav"
    # Audio save karna
    wavfile.write(filename, SAMPLE_RATE, (audio_array * 32767).astype(np.int16))
    temp_wavs.append(filename)

# FFmpeg ke liye list file banana sabhi parts ko jodne ke liye
with open("cod_list.txt", "w") as f:
    for wav in temp_wavs:
        f.write(f"file '{wav}'\n")

raw_combined = "cod_raw_combined.wav"
final_output = "cod_final_1min.mp3"

print("[*] Merging chunks and applying heavy military radio/stadium effects...")
# 1. Sabhi chunks ko concatenate karna
os.system(f"ffmpeg -y -f concat -safe 0 -i cod_list.txt -c copy {raw_combined}")

# 2. FFmpeg se gusse wali aawaz ko aur heavy, overdriven aur radio-broadcast jaisa banana
ffmpeg_cmd = (
    f"ffmpeg -y -i {raw_combined} "
    f"\"-filter:a\" \"volume=3.5,treble=g=10,bass=g=5,compand=attacks=0:points=-80/-80|-45/-30|0/-5\" "
    f"{final_output}"
)
os.system(ffmpeg_cmd)

# Cleanup temporary files
for wav in temp_wavs:
    if os.path.exists(wav):
        os.remove(wav)
if os.path.exists("cod_list.txt"):
    os.remove("cod_list.txt")
if os.path.exists(raw_combined):
    os.remove(raw_combined)

print(f"[+] Success! 1-minute Call of Duty hype voiceover saved as: {final_output}")
