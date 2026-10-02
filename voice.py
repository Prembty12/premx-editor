from transformers import AutoProcessor, AutoModelForTextToSpeech
import scipy.io.wavfile
import torch

# Processor aur model load karna
processor = AutoProcessor.from_pretrained("suno/bark")
model = AutoModelForTextToSpeech.from_pretrained("suno/bark")

# 30-second ka bada, aggressive aur chilaane wala script
text_prompt = (
    "WAIT! STOP SCROLLING RIGHT NOW! [screaming] "
    "What if Spider-Man... finally SNAPPED?! "
    "Imagine New York City burning in absolute CHAOS! Buildings falling down! People screaming for their lives! [shouting] "
    "And the one hero who was supposed to save everyone... is now the biggest monster of them all! "
    "No more holding back! No more mercy! Every single web-slinging battle led to THIS exact moment! "
    "Can anyone stop him before it's too late?! [screaming] "
    "WOAH! You are NOT ready for what happens next! Watch till the end!"
)

# Voice preset (aggressiveness ke liye)
inputs = processor(text_prompt, voice_preset="v2/en_speaker_6")

# Audio generate karna
speech_values = model.generate(**inputs)

# WAV file save karna
scipy.io.wavfile.write("bark_30sec_screaming.wav", rate=model.config.sampling_rate, data=speech_values.cpu().numpy().squeeze())
print("30-second screaming Bark audio generated successfully!")
