import streamlit as st
import os
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="",
    page_icon="",
    layout="wide"
)

# Supported formats
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg', '.wmv', '.flv', '.3gp'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma'}

def is_video_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS

def is_audio_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in AUDIO_EXTENSIONS

def cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except:
        pass

def format_timestamp(seconds: float) -> str:
    """Format seconds to MM:SS.mmm format"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"

class AudioVideoTranscriber:
    def __init__(self, elevenlabs_api_key: str):
        self.elevenlabs_api_key = elevenlabs_api_key.strip() if elevenlabs_api_key and isinstance(elevenlabs_api_key, str) else None

    def convert_to_wav(self, input_path: str, output_path: str) -> bool:
       
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            output_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        except subprocess.CalledProcessError as e:
            st.error(f"FFmpeg conversion failed: {e.stderr}")
            return False
        except Exception as e:
            st.error(f"Conversion error: {e}")
            return False

    def transcribe_with_elevenlabs(self, audio_wav_path: str):
        """"""
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {
            "xi-api-key": self.elevenlabs_api_key
        }
        
        if not os.path.exists(audio_wav_path):
            return {"success": False, "error": f"Audio file not found: {audio_wav_path}"}
        
        try:
            size_mb = os.path.getsize(audio_wav_path) / (1024 * 1024)
            st.info(f"File size: {size_mb:.2f} MB")
            
            with st.spinner(f"Transcribing {size_mb:.2f} MB with ElevenLabs..."):
                with open(audio_wav_path, "rb") as audio_file:
                    files = {
                        'file': ('audio.wav', audio_file, 'audio/wav')
                    }
                    data = {
                        'model_id': 'scribe_v2'  # Valid models: scribe_v1, scribe_v1_experimental, scribe_v2
                    }
                    
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=900)
                    
                    if response.status_code != 200:
                        error_text = response.text[:500]
                        try:
                            error_json = response.json()
                            error_text = str(error_json)
                            # Check for permission errors
                            if response.status_code == 401:
                                detail = error_json.get('detail', {})
                                if detail.get('status') == 'missing_permissions':
                                    return {
                                        "success": False, 
                                        "error": f"ElevenLabs API Error: Your API key doesn't have 'speech_to_text' permission. This feature requires a paid ElevenLabs subscription."
                                    }
                        except:
                            pass
                        return {"success": False, "error": f"ElevenLabs API returned {response.status_code}: {error_text}"}
                    
                    result = response.json()

            # Parse ElevenLabs response - it can return different formats
            full_text = ""
            words = []
            segments = []
            
            # Check if response has 'text' field (simple format)
            if "text" in result:
                full_text = result.get("text", "").strip()
            
            # Check if response has 'words' array (word-level timestamps)
            if "words" in result and isinstance(result["words"], list):
                words = result["words"]
                # Reconstruct full text from words
                full_text = " ".join([word.get("text", "") for word in words if word.get("text")])
            
            # If no words array, try to get text from other fields
            if not full_text:
                full_text = result.get("transcription", "").strip()
            
            if not full_text:
                full_text = str(result).strip()

            # Format timestamped transcript
            timestamped_lines = []
            
            if words:
                # Group words into segments (by sentence or time gaps)
                current_segment = []
                current_start = None
                current_end = None
                
                for word_info in words:
                    word_text = word_info.get("text", "").strip()
                    word_start = word_info.get("start", 0)
                    word_end = word_info.get("end", 0)
                    speaker_id = word_info.get("speaker_id")
                    
                    if not word_text:
                        continue
                    
                    # Start new segment if this is the first word or if there's a significant gap (>2 seconds)
                    if current_start is None or (word_start - current_end) > 2.0:
                        # Save previous segment
                        if current_segment and current_start is not None:
                            segment_text = " ".join(current_segment)
                            start_str = format_timestamp(current_start)
                            end_str = format_timestamp(current_end)
                            speaker_tag = f" [Speaker {speaker_id}]" if speaker_id is not None else ""
                            timestamped_lines.append(f"[{start_str} - {end_str}]{speaker_tag} {segment_text}")
                        
                        # Start new segment
                        current_segment = [word_text]
                        current_start = word_start
                        current_end = word_end
                    else:
                        # Add to current segment
                        current_segment.append(word_text)
                        current_end = word_end
                
                # Add last segment
                if current_segment and current_start is not None:
                    segment_text = " ".join(current_segment)
                    start_str = format_timestamp(current_start)
                    end_str = format_timestamp(current_end)
                    speaker_tag = f" [Speaker {speaker_id}]" if speaker_id is not None else ""
                    timestamped_lines.append(f"[{start_str} - {end_str}]{speaker_tag} {segment_text}")
                
                # Create segments list for JSON output
                segments = []
                for word_info in words:
                    if word_info.get("text"):
                        segments.append({
                            "start": word_info.get("start", 0),
                            "end": word_info.get("end", 0),
                            "text": word_info.get("text", ""),
                            "speaker_id": word_info.get("speaker_id")
                        })
            else:
                # Fallback: if no word-level timestamps, create a single entry
                timestamped_lines.append(f"[00:00.000 - 00:00.000] {full_text}")
                segments = [{"start": 0, "end": 0, "text": full_text}]

            timestamped_transcript = "\n".join(timestamped_lines)

            return {
                "success": True,
                "transcript": full_text,
                "timestamped_transcript": timestamped_transcript,
                "segments": segments,
                "segments_count": len(segments) if segments else 1
            }

        except requests.exceptions.HTTPError as e:
            err_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_detail = e.response.json()
                except:
                    err_detail = e.response.text[:500]
            return {"success": False, "error": f"ElevenLabs API Error ({e.response.status_code if hasattr(e, 'response') and e.response else 'Unknown'}): {err_detail}"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def transcribe_file(self, file_path: str, original_name: str):
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}
        
        temp_wav = None

        try:
            temp_wav = os.path.join(tempfile.gettempdir(), f"transcribe_{os.getpid()}_{os.urandom(4).hex()}.wav")
            
            with st.spinner("Converting to WAV format..."):
                if not self.convert_to_wav(file_path, temp_wav):
                    return {"success": False, "error": "Failed to convert file to WAV. Make sure ffmpeg is installed and the file is valid."}

            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1024:
                return {"success": False, "error": "Converted WAV file is invalid or too small"}

            if not self.elevenlabs_api_key:
                return {"success": False, "error": "ElevenLabs API key not configured"}
            
            return self.transcribe_with_elevenlabs(temp_wav)

        except Exception as e:
            return {"success": False, "error": f"Transcription error: {str(e)}"}
        finally:
            cleanup_file(temp_wav)


# ========================== Streamlit UI ==========================

st.title("")
st.markdown("")

elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")

if not elevenlabs_key:
    st.error("❌ ELEVENLABS_API_KEY not found in .env file. Please add it to your .env file.")
    st.stop()

uploaded_file = st.file_uploader(
    "Upload Audio or Video File",
    type=['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mpg', 'mpeg', 'wmv', 'flv', '3gp', 'mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac', 'wma'],
    help="MP3, WAV, M4A, MP4, MOV, MKV, etc."
)

if uploaded_file:
    suffix = Path(uploaded_file.name).suffix.lower()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(uploaded_file.getvalue())
    temp_file_path = temp_file.name
    temp_file.close()

    try:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        st.info(f"Processing: **{uploaded_file.name}** ({file_size_mb:.1f} MB)")

        if is_video_file(uploaded_file.name):
            st.video(uploaded_file)
        elif is_audio_file(uploaded_file.name):
            st.audio(uploaded_file)

        transcriber = AudioVideoTranscriber(elevenlabs_api_key=elevenlabs_key)
        
        with st.spinner("Converting and transcribing..."):
            result = transcriber.transcribe_file(temp_file_path, uploaded_file.name)

        if result["success"]:
            st.success("✅ Transcription completed successfully!")

            col1, col2 = st.columns(2)
            col1.metric("Segments", result["segments_count"])
            col2.metric("Characters", len(result["transcript"]))

            st.subheader("📝 Timestamped Transcript")
            st.code(result["timestamped_transcript"], language="text")

            st.subheader("📄 Plain Transcript")
            st.text_area("Full text", result["transcript"], height=200, label_visibility="collapsed")

            # Download buttons
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = Path(uploaded_file.name).stem

            col1, col2 = st.columns(2)
            with col1:
                txt = f"""Source: {uploaded_file.name}
Generated: {datetime.now().isoformat()}
Segments: {result["segments_count"]}
{'='*80}

TIMESTAMPED TRANSCRIPT:
{'-'*80}
{result["timestamped_transcript"]}

{'='*80}

FULL TEXT:
{'-'*80}
{result["transcript"]}
"""
                st.download_button("📥 Download .txt", txt, f"{base_name}_transcript_{timestamp}.txt", "text/plain")

            with col2:
                json_out = {
                    "source_file": uploaded_file.name,
                    "generated_at": datetime.now().isoformat(),
                    "transcript": result["transcript"],
                    "timestamped_transcript": result["timestamped_transcript"],
                    "segments": result["segments"],
                    "segments_count": result["segments_count"]
                }
                st.download_button("📥 Download .json", json.dumps(json_out, indent=2, ensure_ascii=False),
                                 f"{base_name}_transcript_{timestamp}.json", "application/json")

        else:
            st.error(f"❌ Transcription failed:\n\n{result.get('error')}")

    finally:
        cleanup_file(temp_file_path)

else:
    st.info("Upload an **audio** (MP3, WAV, etc.) or **video** file to get started!")
  
