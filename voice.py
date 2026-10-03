import os
import subprocess
import torch
from TTS.api import TTS

# Configuration
AUDIO_URL = "https://vocaroo.com/195UOPKZUlpt"
REFERENCE_AUDIO = "voice_sample.wav"
OUTPUT_AUDIO = "cloned_output.wav"
TEXT_TO_SPEAK = "Bhai, yeh wala move dekh kar tumhare hosh ud jayenge! Absolute domination on the battlefield!"

def download_reference_audio():
    print("=== Step 1: Downloading Vocaroo Sample ===")
    if os.path.exists(REFERENCE_AUDIO):
        os.remove(REFERENCE_AUDIO)
        
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "wav",
        "-o", "voice_sample.%(ext)s",
        AUDIO_URL
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[+] Audio successfully downloaded as {REFERENCE_AUDIO}")
    else:
        print(f"[-] Error: {result.stderr}")

def generate_cloned_voice():
    print("\n=== Step 2: Generating Cloned Voice with XTTS ===")
    
    if not os.path.exists(REFERENCE_AUDIO):
        print(f"[-] Error: '{REFERENCE_AUDIO}' file nahi mili!")
        return

    # GitHub Actions CPU par chalega
    device = "cpu"
    print(f"[*] Using device: {device}")
    
    print("[*] Loading XTTS model...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    
    print(f"[*] Converting text to voice: '{TEXT_TO_SPEAK}'")
    
    tts.tts_to_file(
        text=TEXT_TO_SPEAK,
        file_path=OUTPUT_AUDIO,
        speaker_wav=REFERENCE_AUDIO,
        language="en",
        split_sentences=True
    )
    
    print(f"[+] Success! Cloned audio saved as: {OUTPUT_AUDIO}")

if __name__ == "__main__":
    print("=== Voice Cloning Process Started ===")
    download_reference_audio()
    generate_cloned_voice()
    print("=== Process Finished ===")
