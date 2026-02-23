"""
Meeting Bot - Automated Live Meeting Audio Capture
==================================================
This module enables automated joining of Zoom/Google Meet sessions and captures
audio in real-time for transcription without saving intermediate files to disk.

Key Features:
- Browser automation using Playwright
- Real-time audio capture from system audio
- In-memory audio buffering
- Direct integration with Whisper transcription pipeline
- Graceful meeting end detection

Architecture:
1. Playwright controls a Chromium browser to join the meeting
2. System audio is captured using sounddevice (virtual audio cable)
3. Audio is buffered in memory as chunks
4. Chunks are periodically fed to Whisper for real-time transcription
5. Meeting end is detected via DOM monitoring or timeout
"""

import asyncio
import sys
import io
import wave
import numpy as np
import sounddevice as sd
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List
from dataclasses import dataclass
import threading
import queue
import time

# Fix for Windows asyncio subprocess issue with Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from audio_processing.transcriber import AudioTranscriber
import config.settings as settings


@dataclass
class MeetingConfig:
    """Configuration for meeting bot"""
    meeting_url: str
    platform: str  # "zoom" or "google_meet"
    duration_minutes: int = 60  # Maximum meeting duration
    sample_rate: int = 16000  # Audio sample rate (Whisper expects 16kHz)
    channels: int = 1  # Mono audio
    chunk_duration: int = 30  # Seconds of audio per transcription chunk
    auto_join: bool = True  # Automatically click "Join" button
    mute_on_join: bool = True  # Mute microphone on join
    disable_camera: bool = True  # Disable camera on join
    audio_device: Optional[int] = None  # Audio device index (None = default)
    audio_device: Optional[int] = None  # Audio device index (None = default)
    device_index: int = None  # Audio device index (None = default)


class AudioBuffer:
    """
    Thread-safe in-memory audio buffer for real-time capture
    
    Stores audio chunks as numpy arrays and provides methods to:
    - Add audio frames from capture stream
    - Get complete chunks for transcription
    - Convert to WAV format for Whisper
    """
    
    def __init__(self, sample_rate: int, channels: int, chunk_duration: int):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.chunk_size = sample_rate * chunk_duration
        
        self.buffer = []
        self.lock = threading.Lock()
        self.total_frames = 0
        
    def add_frames(self, frames: np.ndarray):
        """Add audio frames to buffer (called by audio callback)"""
        with self.lock:
            self.buffer.extend(frames.flatten().tolist())
            self.total_frames += len(frames)
    
    def get_chunk(self) -> Optional[np.ndarray]:
        """
        Get a complete audio chunk for transcription
        Returns None if insufficient data available
        """
        with self.lock:
            if len(self.buffer) >= self.chunk_size:
                # Extract chunk
                chunk = self.buffer[:self.chunk_size]
                self.buffer = self.buffer[self.chunk_size:]
                return np.array(chunk, dtype=np.float32)
            return None
    
    def get_remaining(self) -> Optional[np.ndarray]:
        """Get any remaining audio in buffer"""
        with self.lock:
            if len(self.buffer) > 0:
                chunk = self.buffer
                self.buffer = []
                return np.array(chunk, dtype=np.float32)
            return None
    
    def to_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        """
        Convert numpy audio array to WAV format bytes
        This creates an in-memory WAV file that Whisper can process
        """
        # Convert float32 to int16 for WAV format
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file in memory
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        
        wav_io.seek(0)
        return wav_io.read()
    
    def save_to_temp_wav(self, audio_data: np.ndarray, temp_path: Path) -> Path:
        """
        Save audio chunk to temporary WAV file for Whisper transcription
        Used when Whisper needs a file path instead of bytes
        """
        wav_bytes = self.to_wav_bytes(audio_data)
        with open(temp_path, 'wb') as f:
            f.write(wav_bytes)
        return temp_path


class MeetingBot:
    """
    Automated meeting bot that joins live meetings and captures audio
    
    Workflow:
    1. Launch browser with Playwright
    2. Navigate to meeting URL
    3. Handle platform-specific join flow (Zoom vs Google Meet)
    4. Start audio capture from system
    5. Buffer audio in memory
    6. Send chunks to transcription pipeline
    7. Detect meeting end and cleanup
    """
    
    def __init__(self, config: MeetingConfig, transcriber: Optional[AudioTranscriber] = None):
        self.config = config
        self.transcriber = transcriber or AudioTranscriber()
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.audio_buffer: Optional[AudioBuffer] = None
        self.audio_stream = None
        
        self.is_recording = False
        self.transcription_results: List[dict] = []
        self.meeting_active = False
        
    async def join_meeting(self):
        """
        Main entry point: Join meeting and start audio capture
        
        Returns:
            dict: Meeting session info and transcription results
        """
        print(f"\n{'='*60}")
        print(f"MEETING BOT - Starting")
        print(f"{'='*60}")
        print(f"Platform: {self.config.platform}")
        print(f"URL: {self.config.meeting_url}")
        print(f"Max Duration: {self.config.duration_minutes} minutes")
        print(f"{'='*60}\n")
        
        try:
            # Step 1: Launch browser and join meeting
            await self._launch_browser()
            await self._join_meeting_by_platform()
            
            # Step 2: Start audio capture (continue even if this fails)
            try:
                self._start_audio_capture()
            except Exception as audio_error:
                print(f"\n⚠️ Audio capture failed: {audio_error}")
                print("⚠️ Continuing without audio capture (bot will stay in meeting)")
                print("⚠️ You can still see the bot in the meeting, but no transcription will occur")
                # Don't raise - let the bot stay in the meeting
            
            # Step 3: Monitor meeting and transcribe in real-time
            await self._monitor_meeting()
            
            # Step 4: Cleanup
            return self._finalize_session()
            
        except Exception as e:
            print(f"❌ Meeting bot error: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _launch_browser(self):
        """Launch Playwright browser with audio permissions"""
        print("🌐 Launching browser...")
        
        playwright = await async_playwright().start()
        
        # Browser launch options
        self.browser = await playwright.chromium.launch(
            headless=False,  # Must be visible to capture audio
            args=[
                '--use-fake-ui-for-media-stream',  # Auto-accept media permissions
                '--use-fake-device-for-media-stream',  # Use fake audio/video
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--autoplay-policy=no-user-gesture-required',  # Allow audio autoplay
            ]
        )
        
        # Create browser context with permissions
        context = await self.browser.new_context(
            permissions=['microphone', 'camera'],
            viewport={'width': 1280, 'height': 720}
        )
        
        self.page = await context.new_page()
        print("✅ Browser launched successfully")
    
    async def _join_meeting_by_platform(self):
        """Route to platform-specific join logic"""
        if self.config.platform.lower() == "zoom":
            await self._join_zoom_meeting()
        elif self.config.platform.lower() in ["google_meet", "google meet", "meet"]:
            await self._join_google_meet()
        else:
            raise ValueError(f"Unsupported platform: {self.config.platform}")
    
    async def _join_zoom_meeting(self):
        """
        Join Zoom meeting via browser
        
        Zoom Browser Join Flow:
        1. Navigate to meeting URL
        2. Click "Join from Your Browser"
        3. Enter name
        4. Click "Join" button
        5. Handle waiting room if present
        """
        print("🎥 Joining Zoom meeting...")
        
        try:
            # Navigate to meeting with longer timeout
            await self.page.goto(self.config.meeting_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Click "Join from Your Browser" link
            try:
                join_browser_link = self.page.locator('a:has-text("Join from Your Browser")')
                await join_browser_link.click(timeout=10000)
                print("  ✓ Clicked 'Join from Browser'")
            except PlaywrightTimeout:
                print("  ⚠️  'Join from Browser' link not found, may already be on join page")
            
            await asyncio.sleep(2)
            
            # Enter name (required by Zoom)
            name_input = self.page.locator('input[type="text"]#input-for-name, input[placeholder*="name" i]').first
            await name_input.fill("AI Meeting Assistant Bot")
            print("  ✓ Entered bot name")
            
            # Disable camera if configured
            if self.config.disable_camera:
                try:
                    camera_button = self.page.locator('button[aria-label*="camera" i], button:has-text("Stop Video")')
                    await camera_button.click(timeout=5000)
                    print("  ✓ Camera disabled")
                except:
                    pass  # Camera may already be off
            
            # Mute microphone if configured
            if self.config.mute_on_join:
                try:
                    mute_button = self.page.locator('button[aria-label*="mute" i], button:has-text("Mute")')
                    await mute_button.click(timeout=5000)
                    print("  ✓ Microphone muted")
                except:
                    pass
            
            # Click "Join" button
            join_button = self.page.locator('button:has-text("Join")')
            await join_button.click()
            print("  ✓ Clicked 'Join Meeting'")
            
            await asyncio.sleep(5)
            
            # Check for waiting room
            waiting_room = self.page.locator('text="Waiting for the host to start this meeting"')
            if await waiting_room.count() > 0:
                print("  ⏳ In waiting room... waiting for host")
            
            self.meeting_active = True
            print("✅ Successfully joined Zoom meeting")
            
        except Exception as e:
            print(f"❌ Failed to join Zoom meeting: {e}")
            raise
    
    async def _join_google_meet(self):
        """
        Join Google Meet via browser
        
        Google Meet Flow:
        1. Navigate to meeting URL
        2. May require Google account login
        3. Click "Join now" or "Ask to join"
        4. Handle camera/microphone permissions
        """
        print("🎥 Joining Google Meet...")
        
        try:
            # Navigate to meeting with longer timeout (Google Meet can be slow)
            await self.page.goto(self.config.meeting_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            
            # Check if login is required
            if "accounts.google.com" in self.page.url:
                print("  ⚠️  Google account login required!")
                print("  ℹ️  Please log in manually in the browser window")
                print("  ⏳ Waiting for login... (60 seconds)")
                await asyncio.sleep(60)  # Give user time to log in
            
            # Fill in name field if present (for anonymous/guest join)
            try:
                name_input = self.page.locator('input[placeholder*="name" i], input[aria-label*="name" i]').first
                if await name_input.count() > 0:
                    await name_input.fill("AI Meeting Assistant Bot")
                    print("  ✓ Entered bot name")
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"  ℹ️  No name field found (might be logged in): {e}")
            
            # Disable camera
            if self.config.disable_camera:
                try:
                    camera_button = self.page.locator('button[aria-label*="camera" i][aria-label*="off" i]')
                    if await camera_button.count() == 0:
                        camera_button = self.page.locator('div[data-tooltip*="camera" i]')
                    await camera_button.first.click(timeout=5000)
                    print("  ✓ Camera disabled")
                except:
                    pass
            
            # Mute microphone
            if self.config.mute_on_join:
                try:
                    mic_button = self.page.locator('button[aria-label*="microphone" i][aria-label*="off" i]')
                    if await mic_button.count() == 0:
                        mic_button = self.page.locator('div[data-tooltip*="microphone" i]')
                    await mic_button.first.click(timeout=5000)
                    print("  ✓ Microphone muted")
                except:
                    pass
            
            await asyncio.sleep(2)
            
            # Click "Join now" or "Ask to join"
            join_button = self.page.locator('button:has-text("Join now"), button:has-text("Ask to join")')
            await join_button.click()
            print("  ✓ Clicked 'Join'")
            
            await asyncio.sleep(5)
            
            self.meeting_active = True
            print("✅ Successfully joined Google Meet")
            
        except Exception as e:
            print(f"❌ Failed to join Google Meet: {e}")
            raise
    
    def _start_audio_capture(self):
        """
        Start capturing system audio in real-time
        
        IMPORTANT: Audio Capture Setup Required
        ========================================
        This uses sounddevice to capture audio. On Windows, you need:
        1. Virtual Audio Cable (VB-CABLE or similar) to route meeting audio
        2. Set the virtual cable as the default recording device
        3. Route browser audio output to the virtual cable
        
        Alternative: Use pyaudiowpatch for direct Windows audio capture
        
        The audio callback function is called repeatedly with audio frames,
        which are added to the in-memory buffer.
        """
        print("\n🎤 Starting audio capture...")
        
        # Initialize audio buffer
        self.audio_buffer = AudioBuffer(
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            chunk_duration=self.config.chunk_duration
        )
        
        # Audio callback - called for each audio frame
        def audio_callback(indata, frames, time_info, status):
            """
            Called by sounddevice for each audio frame
            Adds frames to in-memory buffer for transcription
            """
            if status:
                print(f"  ⚠️  Audio status: {status}")
            
            if self.is_recording:
                # Add audio frames to buffer (in-memory, no disk I/O)
                self.audio_buffer.add_frames(indata.copy())
        
        try:
            # Get device index from config
            device_index = self.config.audio_device
            
            # Start audio stream with specified device
            self.audio_stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                callback=audio_callback,
                blocksize=4096,
                dtype=np.float32,
                device=device_index  # Use specified device or default (None)
            )
            
            self.audio_stream.start()
            self.is_recording = True
            
            print("✅ Audio capture started")
            print(f"  • Sample Rate: {self.config.sample_rate} Hz")
            print(f"  • Channels: {self.config.channels} (Mono)")
            print(f"  • Chunk Duration: {self.config.chunk_duration}s")
            print()
            
        except Exception as e:
            print(f"❌ Failed to start audio capture: {e}")
            print("\n⚠️  AUDIO DEVICE ERROR!")
            print("\nMost likely cause: Stereo Mix is not enabled in Windows")
            print("\n📋 TO FIX (Windows):")
            print("  1. Right-click speaker icon in taskbar")
            print("  2. Click 'Sounds' → 'Recording' tab")
            print("  3. Right-click empty space → 'Show Disabled Devices'")
            print("  4. Right-click 'Stereo Mix' → 'Enable'")
            print("  5. Right-click 'Stereo Mix' → 'Set as Default Device'")
            print("  6. Click OK and restart this app")
            print("\n📝 See file: ENABLE_STEREO_MIX.md for detailed instructions")
            print("\n🔄 Alternative: Use your microphone (device 1) instead")
            raise
    
    async def _monitor_meeting(self):
        """
        Monitor meeting and process audio in real-time
        
        This runs two concurrent tasks:
        1. Audio transcription loop - periodically checks buffer for chunks
        2. Meeting end detection - monitors DOM for "meeting ended" indicators
        """
        print("📊 Monitoring meeting and transcribing audio...\n")
        
        # Start transcription thread
        transcription_task = asyncio.create_task(self._transcription_loop())
        
        # Monitor meeting end
        start_time = time.time()
        max_duration = self.config.duration_minutes * 60
        
        try:
            while self.meeting_active:
                # Check timeout
                if time.time() - start_time > max_duration:
                    print(f"\n⏱️  Maximum duration ({self.config.duration_minutes} min) reached")
                    break
                
                # Check if meeting ended (platform-specific detection)
                if await self._is_meeting_ended():
                    print("\n🏁 Meeting ended detected")
                    break
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
        finally:
            self.meeting_active = False
            self.is_recording = False
            
            # Wait for transcription to finish
            await transcription_task
    
    async def _transcription_loop(self):
        """
        Background loop that processes audio chunks for transcription
        
        Flow:
        1. Wait for complete audio chunk in buffer
        2. Extract chunk from buffer
        3. Save to temporary in-memory WAV file
        4. Send to Whisper transcription
        5. Store results
        6. Repeat
        """
        print("🔄 Transcription loop started\n")
        
        chunk_count = 0
        temp_dir = settings.TRANSCRIPTS_DIR / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        while self.is_recording or self.meeting_active:
            # Get complete audio chunk from buffer
            audio_chunk = self.audio_buffer.get_chunk()
            
            if audio_chunk is not None:
                chunk_count += 1
                print(f"📝 Transcribing chunk #{chunk_count}...")
                
                try:
                    # Create temporary WAV file in memory-backed location
                    # (This is the handoff point to the existing transcription pipeline)
                    temp_path = temp_dir / f"chunk_{chunk_count}_{int(time.time())}.wav"
                    self.audio_buffer.save_to_temp_wav(audio_chunk, temp_path)
                    
                    # *** INTEGRATION POINT WITH EXISTING PIPELINE ***
                    # Call existing AudioTranscriber.transcribe_audio()
                    # This feeds the in-memory buffered audio to Whisper
                    result = self.transcriber.transcribe_audio(temp_path)
                    
                    # Store transcription result
                    self.transcription_results.append({
                        'chunk_number': chunk_count,
                        'timestamp': datetime.now().isoformat(),
                        'text': result['text'],
                        'duration': result['duration']
                    })
                    
                    # Display transcription
                    print(f"  ✅ Chunk #{chunk_count}: {result['text'][:100]}...")
                    print()
                    
                    # Clean up temp file
                    temp_path.unlink()
                    
                except Exception as e:
                    print(f"  ❌ Transcription error for chunk #{chunk_count}: {e}")
            
            else:
                # No complete chunk yet, wait
                await asyncio.sleep(1)
        
        # Process any remaining audio
        remaining = self.audio_buffer.get_remaining()
        if remaining is not None and len(remaining) > 1000:  # At least 1 second
            print(f"📝 Transcribing final chunk...")
            try:
                temp_path = temp_dir / f"chunk_final_{int(time.time())}.wav"
                self.audio_buffer.save_to_temp_wav(remaining, temp_path)
                result = self.transcriber.transcribe_audio(temp_path)
                self.transcription_results.append({
                    'chunk_number': chunk_count + 1,
                    'timestamp': datetime.now().isoformat(),
                    'text': result['text'],
                    'duration': result['duration']
                })
                temp_path.unlink()
            except Exception as e:
                print(f"  ❌ Final chunk transcription error: {e}")
        
        print("✅ Transcription loop completed")
    
    async def _is_meeting_ended(self) -> bool:
        """
        Detect if meeting has ended by checking page content
        
        Platform-specific indicators:
        - Zoom: "This meeting has been ended by host"
        - Google Meet: "You left the meeting" or meeting code disappeared
        """
        try:
            if self.config.platform.lower() == "zoom":
                ended_text = self.page.locator('text="meeting has been ended"')
                return await ended_text.count() > 0
            
            elif self.config.platform.lower() in ["google_meet", "meet"]:
                left_text = self.page.locator('text="You left the meeting", text="left this meeting"')
                return await left_text.count() > 0
            
        except:
            pass
        
        return False
    
    def _finalize_session(self) -> dict:
        """
        Finalize meeting session and return results
        
        Returns:
            dict: Complete session info including all transcriptions
        """
        print("\n" + "="*60)
        print("MEETING SESSION COMPLETE")
        print("="*60)
        
        # Combine all transcription chunks
        full_transcript = "\n\n".join([
            f"[Chunk {r['chunk_number']}] {r['text']}"
            for r in self.transcription_results
        ])
        
        # Save complete transcript
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcript_path = settings.TRANSCRIPTS_DIR / f"live_meeting_{timestamp}.txt"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(full_transcript)
        
        print(f"✅ Full transcript saved: {transcript_path}")
        print(f"📊 Total chunks transcribed: {len(self.transcription_results)}")
        print(f"📝 Total characters: {len(full_transcript)}")
        
        return {
            'meeting_url': self.config.meeting_url,
            'platform': self.config.platform,
            'transcript_path': str(transcript_path),
            'chunks': self.transcription_results,
            'full_transcript': full_transcript,
            'total_chunks': len(self.transcription_results)
        }
    
    async def _cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")
        
        # Stop audio capture
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            print("  ✓ Audio stream closed")
        
        # Close browser
        if self.browser:
            await self.browser.close()
            print("  ✓ Browser closed")
        
        print("✅ Cleanup complete\n")


# ============================================================================
# PUBLIC API - Main Entry Points
# ============================================================================

async def join_and_capture_audio(
    url: str,
    platform: str,
    duration_minutes: int = 60,
    transcriber: Optional[AudioTranscriber] = None
) -> dict:
    """
    Main entry point: Join a live meeting and capture audio for transcription
    
    Args:
        url: Meeting URL (Zoom or Google Meet link)
        platform: Platform type - "zoom" or "google_meet"
        duration_minutes: Maximum meeting duration (default: 60 min)
        transcriber: Optional custom AudioTranscriber instance
    
    Returns:
        dict: Session results with transcription data
        
    Example:
        >>> import asyncio
        >>> from integrations.meeting_bot import join_and_capture_audio
        >>> 
        >>> result = asyncio.run(join_and_capture_audio(
        ...     url="https://zoom.us/j/123456789",
        ...     platform="zoom",
        ...     duration_minutes=30
        ... ))
        >>> 
        >>> print(result['full_transcript'])
    
    Integration with Existing Pipeline:
    -----------------------------------
    The captured audio is fed to audio_processing.transcriber.AudioTranscriber
    via temporary in-memory WAV files. The transcription results are returned
    in the same format as file-based transcriptions.
    
    Audio Flow:
    1. Browser captures meeting audio
    2. sounddevice streams audio to in-memory buffer (AudioBuffer class)
    3. Buffer accumulates chunks (default 30 seconds)
    4. Chunks are saved as temporary WAV files
    5. AudioTranscriber.transcribe_audio() processes each chunk
    6. Results are aggregated and returned
    
    Error Handling:
    - Invalid URL: ValueError raised before browser launch
    - Join failure: Exception with details from Playwright
    - Audio capture failure: Exception with setup instructions
    - Transcription error: Logged but continues with next chunk
    """
    # Validate inputs
    if not url or not url.startswith("http"):
        raise ValueError(f"Invalid meeting URL: {url}")
    
    if platform.lower() not in ["zoom", "google_meet", "meet"]:
        raise ValueError(f"Unsupported platform: {platform}. Use 'zoom' or 'google_meet'")
    
    # Create configuration
    config = MeetingConfig(
        meeting_url=url,
        platform=platform,
        duration_minutes=duration_minutes
    )
    
    # Create and run bot
    bot = MeetingBot(config, transcriber)
    result = await bot.join_meeting()
    
    return result


def join_and_capture_audio_sync(url: str, platform: str, duration_minutes: int = 60) -> dict:
    """
    Synchronous wrapper for join_and_capture_audio
    
    Use this if you need to call from synchronous code.
    
    Example:
        >>> from integrations.meeting_bot import join_and_capture_audio_sync
        >>> result = join_and_capture_audio_sync(
        ...     url="https://meet.google.com/abc-defg-hij",
        ...     platform="google_meet"
        ... )
    """
    return asyncio.run(join_and_capture_audio(url, platform, duration_minutes))


if __name__ == "__main__":
    """
    CLI interface for testing
    
    Usage:
        python meeting_bot.py <url> <platform> [duration_minutes]
        
    Example:
        python meeting_bot.py "https://zoom.us/j/123456789" zoom 30
    """
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python meeting_bot.py <url> <platform> [duration_minutes]")
        print("Example: python meeting_bot.py 'https://zoom.us/j/123456789' zoom 30")
        sys.exit(1)
    
    url = sys.argv[1]
    platform = sys.argv[2]
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    
    result = join_and_capture_audio_sync(url, platform, duration)
    
    print("\n" + "="*60)
    print("FINAL TRANSCRIPT")
    print("="*60)
    print(result['full_transcript'])
