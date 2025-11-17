import streamlit as st
import os
import tempfile
import subprocess
import requests
from pathlib import Path
from datetime import datetime
import json
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Video Transcriber", page_icon="🎬", layout="wide")


# -----------------------------
# CLASS: Video Transcriber
# -----------------------------
class VideoTranscriber:
    def __init__(self, openai_api_key: str):
        self.api_key = openai_api_key

    # -----------------------------
    # Extract audio from video
    # -----------------------------
    def extract_audio(self, video_path: str, audio_path: str):
        try:
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
        except Exception:
            return False

    # -----------------------------
    # Convert any audio to WAV 
    # -----------------------------
    def convert_audio_to_wav(self, input_path: str, output_path: str):
        try:
            cmd = [
                "ffmpeg", "-i", input_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return os.path.exists(output_path)
        except Exception:
            return False

    # -----------------------------
    # NEW OpenAI Transcription API
    # -----------------------------
    def transcribe_audio(self, wav_path: str):
        url = "https://api.openai.com/v1/responses"

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        with open(wav_path, "rb") as f:
            files = {
                "model": (None, "gpt-4o-mini-transcribe"),
                "input_audio": ("audio.wav", f, "audio/wav"),
                "response_format": (None, "text")
            }

            response = requests.post(url, headers=headers, files=files)

        if response.status_code != 200:
            return {
                "success": False,
                "error": response.text
            }

        text_output = response.json()["output"][0]["content"][0]["text"]

        return {
            "success": True,
            "transcript": text_output
        }

    # -----------------------------
    # Main pipeline
    # -----------------------------
    def process_file(self, file_path: str, extension: str):
        tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

        is_video = extension in [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        is_audio = extension in [".mp3", ".wav", ".m4a", ".aac"]

        # Extract or convert audio
        if is_video:
            ok = self.extract_audio(file_path, tmp_wav)
        else:
            ok = self.convert_audio_to_wav(file_path, tmp_wav)

        if not ok:
            return {"success": False, "error": "Audio extraction failed"}

        # Transcribe
        result = self.transcribe_audio(tmp_wav)

        # Cleanup
        try:
            os.remove(tmp_wav)
        except:
            pass

        return result


# -----------------------------
# STREAMLIT UI
# -----------------------------
st.title("🎬 Video / Audio Transcriber (OpenAI 2025 API)")

api_key = os.getenv("OPEN_API_KEY")
if not api_key:
    st.error("❌ OPEN_API_KEY missing in .env file.")
    st.stop()

uploaded_file = st.file_uploader(
    "Upload Video or Audio",
    type=["mp4", "avi", "mov", "mkv", "webm", "mp3", "wav", "m4a", "aac"]
)

if uploaded_file:
    file_ext = Path(uploaded_file.name).suffix.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    transcriber = VideoTranscriber(api_key)

    with st.spinner("Processing file..."):
        result = transcriber.process_file(tmp_path, file_ext)

    # Cleanup
    try:
        os.remove(tmp_path)
    except:
        pass

    # Show result
    if result["success"]:
        transcript = result["transcript"]

        st.success("✅ Transcription complete!")
        st.text_area("Transcript", transcript, height=400)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_root = Path(uploaded_file.name).stem

        st.download_button(
            "📥 Download Transcript (.txt)",
            transcript,
            file_name=f"{file_root}_transcript_{timestamp}.txt"
        )

        st.download_button(
            "📥 Download Transcript (.json)",
            json.dumps({"transcript": transcript}, indent=2),
            file_name=f"{file_root}_transcript_{timestamp}.json"
        )

    else:
        st.error(f"❌ Error: {result['error']}")
else:
    st.info("Upload a video/audio file to begin.")
