import os
import torch
import torch.serialization
import numpy as np
import wave

# PyTorch 2.6 Unpickling & Weights Only Fix
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load

from bark import SAMPLE_RATE, generate_audio, preload_models

# CPU mode force karna GitHub Actions ke liye
os.environ["SUNO_OFFLOAD_CPU"] = "True"
os.environ["SUNO_USE_SMALL_MODELS"] = "True"

print("[*] Loading Bark AI Models...")
preload_models()

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
    audio_array = generate_audio(text, history_prompt="v2/en_speaker_6")
    
    filename = f"chunk_{i}.wav"
    audio_int16 = (audio_array * 32767).astype(np.int16)
    
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio_int16.tobytes())
        
    temp_wavs.append(filename)

final_output = "cod_final_pure.wav"
print("[*] Merging chunks using pure Python...")

data = []
for wav_file in temp_wavs:
    with wave.open(wav_file, 'rb') as w:
        data.append(w.readframes(w.getnframes()))

with wave.open(final_output, 'wb') as final_wav:
    final_wav.setnchannels(1)
    final_wav.setsampwidth(2)
    final_wav.setframerate(SAMPLE_RATE)
    for block in data:
        final_wav.writeframes(block)

for wav in temp_wavs:
    if os.path.exists(wav):
        os.remove(wav)

print(f"[+] Success! Pure AI voiceover saved as: {final_output}")
