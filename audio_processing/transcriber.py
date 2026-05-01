"""
Audio transcription using Groq Cloud Whisper API
"""
import os
from pathlib import Path
from groq import Groq
import config.settings as settings

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
        
        self.ffmpeg_available = True  # We don't need local FFmpeg anymore for native Python fallback to matter
        print("[SUCCESS] Groq Audio API initialized successfully")

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
            
            # Use Groq API
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
