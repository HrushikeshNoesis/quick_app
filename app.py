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
    page_title="Video Transcriber with Timestamps",
    page_icon="🎬",
    layout="wide"
)

class VideoTranscriber:
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
    
    def extract_audio_from_video(self, video_path: str, audio_path: str) -> bool:
        try:
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                return True
            else:
                st.error(f"FFmpeg extraction failed: {result.stderr}")
                return False
                
        except Exception as e:
            st.error(f"Failed to extract audio from video: {e}")
            return False
    
    def optimize_audio_for_whisper(self, audio_path: str) -> str:
        try:
            optimized_path = audio_path.replace('.wav', '_optimized.wav')
            
            cmd = [
                'ffmpeg', '-i', audio_path,
                '-af', 'highpass=f=80,lowpass=f=8000,volume=1.5',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                optimized_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(optimized_path):
                os.replace(optimized_path, audio_path)
                return audio_path
            else:
                return audio_path
                
        except Exception as e:
            return audio_path
    
    def transcribe_audio_with_whisper(self, audio_path: str):
        try:
            optimized_path = self.optimize_audio_for_whisper(audio_path)
            
            url = "https://api.openai.com/v1/audio/transcriptions"
            
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            with open(optimized_path, 'rb') as audio_file:
                files = {
                    'file': (os.path.basename(audio_path), audio_file, 'audio/wav'),
                    'model': (None, 'whisper-1'),
                    'response_format': (None, 'verbose_json'),
                    'timestamp_granularities': (None, '["segment"]')
                }
                
                file_size = os.path.getsize(optimized_path)
                st.info(f"Sending audio to OpenAI Whisper: {file_size / 1024 / 1024:.2f} MB")
                
                response = requests.post(url, headers=headers, files=files, timeout=300)
                response.raise_for_status()
                
                result = response.json()
                
                full_text = result.get("text", "")
                segments = result.get("segments", [])
                timestamped_text = ""
                
                for segment in segments:
                    start_time = segment.get("start", 0)
                    end_time = segment.get("end", 0)
                    text = segment.get("text", "").strip()
                    confidence = segment.get("avg_logprob", 0)
                    
                    start_formatted = f"{int(start_time//60):02d}:{int(start_time%60):02d}"
                    end_formatted = f"{int(end_time//60):02d}:{int(end_time%60):02d}"
                    
                    confidence_indicator = " [LOW_CONFIDENCE]" if confidence < -0.5 else ""
                    timestamped_text += f"[{start_formatted} - {end_formatted}] {text}{confidence_indicator}\n"
                
                return {
                    'success': True,
                    'transcript': full_text,
                    'timestamped_transcript': timestamped_text.strip(),
                    'segments_count': len(segments),
                    'segments': segments,
                    'error': None
                }
                
        except Exception as e:
            return {
                'success': False,
                'transcript': '',
                'timestamped_transcript': '',
                'segments_count': 0,
                'segments': [],
                'error': str(e)
            }
    
    def transcribe_video(self, video_path: str):
        if not os.path.exists(video_path):
            return {
                'success': False,
                'error': f'Video file not found: {video_path}'
            }
        
        video_name = Path(video_path).stem
        temp_audio_path = os.path.join(tempfile.gettempdir(), f'{video_name}_audio.wav')
        
        try:
            with st.spinner("Extracting audio from video..."):
                if not self.extract_audio_from_video(video_path, temp_audio_path):
                    return {
                        'success': False,
                        'error': 'Failed to extract audio from video'
                    }
            
            with st.spinner("Transcribing audio with Whisper..."):
                transcription_result = self.transcribe_audio_with_whisper(temp_audio_path)
            
            if not transcription_result['success']:
                return {
                    'success': False,
                    'error': transcription_result.get('error', 'Transcription failed')
                }
            
            return {
                'success': True,
                'transcript': transcription_result['transcript'],
                'timestamped_transcript': transcription_result['timestamped_transcript'],
                'segments_count': transcription_result['segments_count'],
                'segments': transcription_result['segments'],
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
        
        finally:
            try:
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
            except:
                pass

st.title("🎬 Video Transcriber with Timestamps")

api_key = os.getenv("OPEN_API_KEY")
if not api_key:
    st.error("❌ OPEN_API_KEY not found in .env file. Please add it to your .env file.")
    st.stop()

uploaded_file = st.file_uploader(
    "Upload Video File",
    type=['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv'],
    help="Upload a video file to transcribe"
)

if uploaded_file is not None:
    if not api_key:
        st.error("❌ Please enter your OpenAI API key in the sidebar")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
        
        try:
            st.info(f"📹 Processing: {uploaded_file.name}")
            
            transcriber = VideoTranscriber(api_key)
            result = transcriber.transcribe_video(tmp_file_path)
            
            if result['success']:
                st.success("✅ Transcription completed successfully!")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Segments", result['segments_count'])
                with col2:
                    st.metric("Transcript Length", f"{len(result['transcript'])} characters")
                
                st.header("📄 Timestamped Transcript")
                st.text_area(
                    "Timestamped Transcript",
                    value=result['timestamped_transcript'],
                    height=400,
                    label_visibility="collapsed"
                )
                
                st.header("📝 Full Transcript (No Timestamps)")
                st.text_area(
                    "Full Transcript",
                    value=result['transcript'],
                    height=300,
                    label_visibility="collapsed"
                )
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_name = Path(uploaded_file.name).stem
                
                col1, col2 = st.columns(2)
                
                with col1:
                    txt_content = f"Video Transcript: {uploaded_file.name}\n"
                    txt_content += f"Generated: {datetime.now().isoformat()}\n"
                    txt_content += f"Total segments: {result['segments_count']}\n"
                    txt_content += "=" * 80 + "\n\n"
                    txt_content += "TIMESTAMPED TRANSCRIPT:\n"
                    txt_content += "-" * 80 + "\n"
                    txt_content += result['timestamped_transcript']
                    txt_content += "\n\n" + "=" * 80 + "\n\n"
                    txt_content += "FULL TRANSCRIPT (NO TIMESTAMPS):\n"
                    txt_content += "-" * 80 + "\n"
                    txt_content += result['transcript']
                    
                    st.download_button(
                        label="📥 Download Text File",
                        data=txt_content,
                        file_name=f"{video_name}_transcript_{timestamp}.txt",
                        mime="text/plain"
                    )
                
                with col2:
                    json_data = {
                        'video_file': uploaded_file.name,
                        'generated_at': datetime.now().isoformat(),
                        'transcript': result['transcript'],
                        'timestamped_transcript': result['timestamped_transcript'],
                        'segments_count': result['segments_count'],
                        'segments': result['segments']
                    }
                    
                    st.download_button(
                        label="📥 Download JSON File",
                        data=json.dumps(json_data, indent=2, ensure_ascii=False),
                        file_name=f"{video_name}_transcript_{timestamp}.json",
                        mime="application/json"
                    )
                
            else:
                st.error(f"❌ Transcription failed: {result.get('error', 'Unknown error')}")
        
        finally:
            try:
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
            except:
                pass

else:
    st.info("👆 Please upload a video file to get started")
