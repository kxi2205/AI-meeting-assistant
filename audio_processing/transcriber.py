"""
Audio transcription using OpenAI Whisper
"""
import whisper
import torch
from pathlib import Path
import config.settings as settings

class AudioTranscriber:
    """Handles audio transcription using Whisper"""
    
    def __init__(self, model_name=None, device=None):
        """
        Initialize the transcriber
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large, large-v3)
            device: Device to run on (cpu, cuda)
        """
        self.model_name = model_name or settings.WHISPER_MODEL
        self.device = device or settings.WHISPER_DEVICE
        
        print(f"Loading Whisper model: {self.model_name}...")
        self.model = whisper.load_model(self.model_name, device=self.device)
        print("✓ Whisper model loaded successfully")
    
    def transcribe_audio(self, audio_path, language=None):
        """
        Transcribe audio file to text
        
        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'en', 'es'). None for auto-detect
        
        Returns:
            dict: Transcription results with text, segments, and metadata
        """
        try:
            print(f"Transcribing: {audio_path}")
            
            # Transcribe
            result = self.model.transcribe(
                str(audio_path),
                language=language,
                verbose=False
            )
            
            # Extract key information
            transcription = {
                'text': result['text'].strip(),
                'language': result.get('language', 'unknown'),
                'segments': result.get('segments', []),
                'duration': result.get('segments', [{}])[-1].get('end', 0) if result.get('segments') else 0
            }
            
            # Save transcript to file
            self._save_transcript(audio_path, transcription['text'])
            
            print(f"✓ Transcription complete ({len(transcription['text'])} characters)")
            return transcription
            
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            raise
    
    def _save_transcript(self, audio_path, text):
        """Save transcript to text file"""
        audio_path = Path(audio_path)
        transcript_path = settings.TRANSCRIPTS_DIR / f"{audio_path.stem}_transcript.txt"
        
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"✓ Transcript saved to: {transcript_path}")
    
    def get_model_info(self):
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'device': self.device,
            'parameters': sum(p.numel() for p in self.model.parameters())
        }
