import os
import whisper

def main():
    audio_path = "my_voice.m4a"
    output_path = "transcript.txt"
    
    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} nahi mili repository mein.")
        return

    print("Whisper model load ho raha hai (base/small)...")
    model = whisper.load_model("base")

    print(f"'{audio_path}' transcribe ho rahi hai with detailed timestamps...")
    result = model.transcribe(audio_path, verbose=False)

    print(f"Transcript save ho raha hai: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for segment in result["segments"]:
            start = segment["start"]
            end = segment["end"]
            text = segment["text"].strip()
            f.write(f"[{format_time(start)} --> {format_time(end)}] {text}\n")

    print("Transcription successfully complete ho gayi!")

def format_time(seconds):
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:06.3f}"

if __name__ == "__main__":
    main()
