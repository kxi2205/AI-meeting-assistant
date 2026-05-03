"""
Audio transcription using Groq Cloud Whisper API
"""
import os
import asyncio
import subprocess
import math
import tempfile
import shutil
from pathlib import Path
from groq import Groq, AsyncGroq
import config.settings as settings
from datetime import datetime

class AudioTranscriber:
    """Handles audio transcription using Groq Whisper API"""
    
    def __init__(self, model_name="whisper-large-v3", device=None):
        """
        Initialize the transcriber
        
        Args:
            model_name: Groq whisper model (default: whisper-large-v3)
            device: Ignored, kept for API compatibility with old transcriber
        """
        self.model_name = model_name
        
        print(f"Loading Groq Whisper client for model: {self.model_name}...")
        
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in environment variables")
            
        self.client = Groq(
            api_key=settings.GROQ_API_KEY,
            max_retries=3
        )
        self.async_client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            max_retries=3
        )
        
        self.ffmpeg_available = True
        print("[SUCCESS] Groq Audio API initialized successfully (Parallel Chunking Enabled)")

    def transcribe_audio(self, audio_path, language=None, prompt=""):
        """
        Transcribe audio file to text
        
        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'en', 'es'). None for auto-detect
            prompt: Text to guide transcription (useful for proper nouns and context)
        
        Returns:
            dict: Transcription results with text, segments, and metadata
        """
        try:
            # Check file size (Groq limit is 25MB)
            file_size = os.path.getsize(str(audio_path))
            if file_size > 24 * 1024 * 1024:  # 24MB threshold
                print(f"[INFO] Large file detected ({file_size / 1024 / 1024:.2f} MB). Starting parallel chunked transcription...")
                return asyncio.run(self._split_and_transcribe(audio_path, language, prompt))

            print(f"Transcribing via Groq Cloud: {audio_path}")
            
            # Setup optional kwargs based on API spec
            kwargs = {
                "model": self.model_name,
                "response_format": "verbose_json",
            }
            if language and language != "auto":
                kwargs["language"] = language
            if prompt and prompt.strip():
                kwargs["prompt"] = prompt.strip()
            
            # Use Groq API (Synchronous for small files)
            with open(str(audio_path), "rb") as file:
                kwargs["file"] = (os.path.basename(audio_path), file.read())
                response = self.client.audio.transcriptions.create(**kwargs)
            
            # Extract key information
            transcription = {
                'text': response.text.strip(),
                'language': getattr(response, 'language', 'unknown'),
                'segments': getattr(response, 'segments', []),
                'duration': getattr(response, 'duration', 0)
            }
            
            # Save transcript to file
            self._save_transcript(audio_path, transcription['text'])
            
            print(f"[SUCCESS] Cloud Transcription complete ({len(transcription['text'])} characters)")
            return transcription
            
        except Exception as e:
            print(f"[ERROR] Groq Transcription error: {e}")
            raise

    async def _split_and_transcribe(self, audio_path, language=None, prompt=""):
        """Split large audio into chunks and transcribe in parallel"""
        temp_dir = Path(tempfile.mkdtemp(prefix="meeting_chunks_"))
        try:
            # 1. Split audio using FFmpeg (fast stream copy)
            # We use 10-minute segments as a safe default that usually stays under 25MB
            print(f"[INFO] Splitting audio into segments...")
            segment_pattern = temp_dir / "chunk_%03d.mp3"
            
            ffmpeg_exe = settings.FFMPEG_BINARY_PATH or 'ffmpeg'
            split_cmd = [
                ffmpeg_exe, '-i', str(audio_path),
                '-f', 'segment',
                '-segment_time', '600', # 10 minutes
                '-c', 'copy',
                str(segment_pattern)
            ]
            subprocess.run(split_cmd, check=True, capture_output=True)
            
            chunks = sorted(list(temp_dir.glob("chunk_*.mp3")))
            print(f"[INFO] Created {len(chunks)} chunks for parallel processing.")

            # 2. Transcribe chunks in parallel
            tasks = []
            for i, chunk_path in enumerate(chunks):
                tasks.append(self._transcribe_chunk_async(chunk_path, language, prompt, i))
            
            results = await asyncio.gather(*tasks)
            
            # 3. Combine results in order
            results.sort(key=lambda x: x['index'])
            combined_text = " ".join([r['text'] for r in results])
            total_duration = sum([r['duration'] for r in results])
            
            final_transcription = {
                'text': combined_text.strip(),
                'language': results[0]['language'] if results else 'unknown',
                'segments': [], # Could flatten segments if needed, but text is priority
                'duration': total_duration
            }
            
            # Save final transcript
            self._save_transcript(audio_path, final_transcription['text'])
            print(f"[SUCCESS] Parallel transcription complete. Total characters: {len(combined_text)}")
            return final_transcription

        finally:
            # Cleanup temp files
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _transcribe_chunk_async(self, chunk_path, language, prompt, index):
        """Internal helper for async chunk transcription"""
        try:
            kwargs = {
                "model": self.model_name,
                "response_format": "verbose_json",
            }
            if language and language != "auto":
                kwargs["language"] = language
            if prompt and prompt.strip():
                kwargs["prompt"] = prompt.strip()
                
            with open(str(chunk_path), "rb") as file:
                kwargs["file"] = (os.path.basename(chunk_path), file.read())
                response = await self.async_client.audio.transcriptions.create(**kwargs)
                
            return {
                'index': index,
                'text': response.text.strip(),
                'language': getattr(response, 'language', 'unknown'),
                'duration': getattr(response, 'duration', 0)
            }
        except Exception as e:
            print(f"[ERROR] Chunk #{index} transcription failed: {e}")
            return {'index': index, 'text': "", 'language': 'unknown', 'duration': 0}
    
    def _save_transcript(self, audio_path, text):
        """Save transcript to text file"""
        audio_path = Path(audio_path)
        transcript_path = settings.TRANSCRIPTS_DIR / f"{audio_path.stem}_transcript.txt"
        
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"[SUCCESS] Transcript saved to: {transcript_path}")
    
    def get_model_info(self):
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'device': "cloud (Groq)",
            'parameters': "N/A"
        }
