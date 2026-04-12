"""
Audio transcription using OpenAI Whisper
"""
import whisper
import torch
import subprocess
import os
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
        
        # Verify FFmpeg
        self._verify_ffmpeg()

    def _verify_ffmpeg(self):
        """Check if FFmpeg is installed, otherwise transcription will fail"""
        # 1. Try standard system path
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            print("✓ FFmpeg verification successful (System Path)")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # 2. Try hardcoded winget path
        winget_bin = r"C:\Users\khush\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
        ffmpeg_exe = os.path.join(winget_bin, "ffmpeg.exe")
        
        if os.path.exists(ffmpeg_exe):
            try:
                # Add to path for this session
                if winget_bin not in os.environ["PATH"]:
                    os.environ["PATH"] += os.pathsep + winget_bin
                
                # Check if it works now
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
                print(f"✓ FFmpeg verified at winget location")
                return
            except:
                pass

        # 3. Try imageio-ffmpeg fallback
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_executable()
            if ffmpeg_path:
                print("ℹ️ Using imageio-ffmpeg as fallback...")
                return
        except ImportError:
            pass

        # 4. If all else fails, show the critical error instructions
        print("\n" + "!"*60)
        print("CRITICAL ERROR: FFmpeg not found!")
        print("Whisper transcription requires FFmpeg to be installed.")
        print("\nTO FIX (Windows):")
        print("  1. Run this command in a new terminal:  winget install ffmpeg")
        print("  2. Restart the app after installation.")
        print("!"*60 + "\n")
    
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
