import streamlit as st
import os
import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
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
    """Format seconds to HH:MM:SS.mmm format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"

def needs_conversion(file_path: str) -> bool:
    """Check if file needs conversion to WAV"""
    ext = Path(file_path).suffix.lower()
    if ext == '.wav':
        # Check if it's already in the right format (16kHz mono)
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', 
                   '-show_entries', 'stream=sample_rate,channels', 
                   '-of', 'json', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                streams = probe_data.get('streams', [])
                if streams:
                    sample_rate = int(streams[0].get('sample_rate', 0))
                    channels = int(streams[0].get('channels', 0))
                    if sample_rate == 16000 and channels == 1:
                        return False
        except:
            pass
    return True

class AudioVideoTranscriber:
    def __init__(self, elevenlabs_api_key: str):
        self.elevenlabs_api_key = elevenlabs_api_key.strip() if elevenlabs_api_key and isinstance(elevenlabs_api_key, str) else None

    def convert_to_wav(self, input_path: str, output_path: str, progress_bar=None, status_text=None) -> bool:
        """Convert audio/video to optimized WAV format with progress tracking"""
        # Optimized ffmpeg command for faster conversion
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            "-threads", "0",  # Use all available threads
            "-loglevel", "error",  # Reduce logging overhead
            output_path
        ]
        try:
            start_time = time.time()
            if progress_bar:
                progress_bar.progress(0.1)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                elapsed = time.time() - start_time
                if status_text:
                    status_text.text(f"✅ Conversion completed in {elapsed:.1f}s")
                if progress_bar:
                    progress_bar.progress(0.2)
                return True
            else:
                if status_text:
                    status_text.text(f"❌ Conversion failed: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            if status_text:
                status_text.text("❌ Conversion timed out")
            return False
        except Exception as e:
            if status_text:
                status_text.text(f"❌ Conversion error: {str(e)[:200]}")
            return False

    def transcribe_with_elevenlabs(self, audio_wav_path: str, progress_bar=None, status_text=None, start_progress=0.2):
        """Transcribe using ElevenLabs Speech-to-Text API with progress tracking"""
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {
            "xi-api-key": self.elevenlabs_api_key
        }
        
        if not os.path.exists(audio_wav_path):
            return {"success": False, "error": f"Audio file not found: {audio_wav_path}"}
        
        try:
            size_mb = os.path.getsize(audio_wav_path) / (1024 * 1024)
            file_duration = self._estimate_duration(audio_wav_path)
            
            # Progress range: start_progress to 1.0 (80% of total progress for transcription)
            progress_range = 1.0 - start_progress
            
            if status_text:
                status_text.text(f"📤 Uploading {size_mb:.2f} MB to ElevenLabs...")
            if progress_bar:
                progress_bar.progress(start_progress + progress_range * 0.1)
            
            start_time = time.time()
            
            with open(audio_wav_path, "rb") as audio_file:
                files = {
                    'file': ('audio.wav', audio_file, 'audio/wav')
                }
                data = {
                    'model_id': 'scribe_v2'
                }
                
                if status_text:
                    status_text.text(f"🔄 Transcribing with ElevenLabs (estimated {file_duration:.0f}s audio)...")
                if progress_bar:
                    progress_bar.progress(start_progress + progress_range * 0.3)
                
                response = requests.post(url, headers=headers, files=files, data=data, timeout=900)
                
                if progress_bar:
                    progress_bar.progress(start_progress + progress_range * 0.7)
                
                if response.status_code != 200:
                    error_text = response.text[:500]
                    try:
                        error_json = response.json()
                        error_text = str(error_json)
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
                
                if progress_bar:
                    progress_bar.progress(start_progress + progress_range * 0.85)

            # Parse ElevenLabs response
            full_text = ""
            words = []
            segments = []
            
            if "text" in result:
                full_text = result.get("text", "").strip()
            
            if "words" in result and isinstance(result["words"], list):
                words = result["words"]
                full_text = " ".join([word.get("text", "") for word in words if word.get("text")])
            
            if not full_text:
                full_text = result.get("transcription", "").strip()
            
            if not full_text:
                full_text = str(result).strip()

            if status_text:
                status_text.text("📝 Processing timestamps...")
            if progress_bar:
                progress_bar.progress(start_progress + progress_range * 0.95)

            # Improved timestamp formatting with better segmentation
            timestamped_lines = []
            
            if words:
                # Smart segmentation: group by natural pauses and sentence boundaries
                current_segment = []
                current_start = None
                current_end = None
                current_speaker = None
                pause_threshold = 1.0  # 1 second pause creates new segment
                max_segment_duration = 10.0  # Max 10 seconds per segment
                
                for word_info in words:
                    word_text = word_info.get("text", "").strip()
                    word_start = word_info.get("start", 0)
                    word_end = word_info.get("end", 0)
                    speaker_id = word_info.get("speaker_id")
                    
                    if not word_text:
                        continue
                    
                    # Check for new segment conditions
                    gap = word_start - current_end if current_end is not None else 0
                    segment_duration = (current_end - current_start) if current_start is not None else 0
                    speaker_changed = (speaker_id is not None and current_speaker is not None and speaker_id != current_speaker)
                    
                    should_start_new = (
                        current_start is None or  # First word
                        gap > pause_threshold or  # Significant pause
                        segment_duration > max_segment_duration or  # Segment too long
                        speaker_changed  # Speaker changed
                    )
                    
                    if should_start_new:
                        # Save previous segment
                        if current_segment and current_start is not None:
                            segment_text = " ".join(current_segment)
                            start_str = format_timestamp(current_start)
                            end_str = format_timestamp(current_end)
                            speaker_tag = f" [Speaker {current_speaker}]" if current_speaker is not None else ""
                            timestamped_lines.append(f"[{start_str} - {end_str}]{speaker_tag} {segment_text}")
                        
                        # Start new segment
                        current_segment = [word_text]
                        current_start = word_start
                        current_end = word_end
                        current_speaker = speaker_id
                    else:
                        # Add to current segment
                        current_segment.append(word_text)
                        current_end = word_end
                        if speaker_id is not None:
                            current_speaker = speaker_id
                
                # Add last segment
                if current_segment and current_start is not None:
                    segment_text = " ".join(current_segment)
                    start_str = format_timestamp(current_start)
                    end_str = format_timestamp(current_end)
                    speaker_tag = f" [Speaker {current_speaker}]" if current_speaker is not None else ""
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
                timestamped_lines.append(f"[00:00.000 - 00:00.000] {full_text}")
                segments = [{"start": 0, "end": 0, "text": full_text}]

            timestamped_transcript = "\n".join(timestamped_lines)
            
            elapsed = time.time() - start_time
            
            if status_text:
                status_text.text(f"✅ Transcription completed in {elapsed:.1f}s")
            if progress_bar:
                progress_bar.progress(1.0)

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
    
    def _estimate_duration(self, audio_path: str) -> float:
        """Estimate audio duration using ffprobe"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                   '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 0.0

    def transcribe_file(self, file_path: str, original_name: str, progress_bar=None, status_text=None):
        """Main transcription method with progress tracking"""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}
        
        temp_wav = None

        try:
            # Check if conversion is needed
            needs_conv = needs_conversion(file_path)
            
            if needs_conv:
                temp_wav = os.path.join(tempfile.gettempdir(), f"transcribe_{os.getpid()}_{os.urandom(4).hex()}.wav")
                
                if status_text:
                    status_text.text("🔄 Converting to optimized audio format...")
                if progress_bar:
                    progress_bar.progress(0.05)
                
                if not self.convert_to_wav(file_path, temp_wav, progress_bar, status_text):
                    return {"success": False, "error": "Failed to convert file to WAV. Make sure ffmpeg is installed and the file is valid."}

                if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1024:
                    return {"success": False, "error": "Converted WAV file is invalid or too small"}
                
                audio_file = temp_wav
                conversion_done = True
            else:
                # File is already in correct format
                if status_text:
                    status_text.text("✅ File format is already optimized, skipping conversion...")
                if progress_bar:
                    progress_bar.progress(0.2)
                audio_file = file_path
                conversion_done = False

            if not self.elevenlabs_api_key:
                return {"success": False, "error": "ElevenLabs API key not configured"}
            
            # Adjust progress start based on whether conversion happened
            if conversion_done:
                # Conversion took us to 0.2, transcription starts from there
                return self.transcribe_with_elevenlabs(audio_file, progress_bar, status_text, start_progress=0.2)
            else:
                # No conversion, transcription starts from 0.2
                return self.transcribe_with_elevenlabs(audio_file, progress_bar, status_text, start_progress=0.2)

        except Exception as e:
            return {"success": False, "error": f"Transcription error: {str(e)}"}
        finally:
            if temp_wav:
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
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        result = transcriber.transcribe_file(temp_file_path, uploaded_file.name, progress_bar, status_text)

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
  
