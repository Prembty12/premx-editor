import os
import whisper

def main():
    audio_path = "audio.mp3"
    output_path = "transcript.txt"
    
    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} nahi mili repository mein.")
        return

    print("Whisper model load ho raha hai (base/small)...")
    # Aap 'base', 'small', ya 'medium' model select kar sakte hain
    model = whisper.load_model("base")

    print("Audio transcribe ho rahi hai with detailed timestamps...")
    result = model.transcribe(audio_path, verbose=False)

    print(f"Transcript save ho raha hai: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for segment in result["segments"]:
            start = segment["start"]
            end = segment["end"]
            text = segment["text"].strip()
            # Format: [00:00.000 --> 00:05.000] Text here
            f.write(f"[{format_time(start)} --> {format_time(end)}] {text}\n")

    print("Transcription successfully complete ho gayi!")

def format_time(seconds):
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:06.3f}"

if __name__ == "__main__":
    main()
