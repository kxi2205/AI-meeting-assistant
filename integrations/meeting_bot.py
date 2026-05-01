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
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from audio_processing.transcriber import AudioTranscriber
import config.settings as settings
from integrations.bot_manager import bot_manager


@dataclass
class MeetingConfig:
    """Configuration for meeting bot"""
    meeting_url: str
    platform: str  # "zoom" or "google_meet"
    duration_minutes: int = 60  # Maximum meeting duration
    sample_rate: int = 16000  # Audio sample rate (Whisper expects 16kHz)
    channels: int = 1  # Mono audio
    chunk_duration: int = 5  # Reduced from 30 to 5 seconds for fast termination
    auto_join: bool = True  # Automatically click "Join" button
    mute_on_join: bool = True  # Mute microphone on join
    disable_camera: bool = True  # Disable camera on join
    audio_device: Optional[int] = None  # Audio device index (None = default)
    headless: bool = True  # Run browser in headless mode (invisible)
    
    # Calendar Integration Metadata
    linked_account: Optional[str] = None
    calendar_event_id: Optional[str] = None
    invitees: Optional[list] = None
    bot_name: str = settings.BOT_NAME  # Name to use when joining
    prompt_context: str = ""  # Initial prompt for Whisper to learn proper noun spellings


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
        
        # Use numpy arrays exclusively for memory efficiency
        self.buffer = np.array([], dtype=np.float32)
        self.lock = threading.Lock()
        self.total_frames = 0
        
    def add_frames(self, frames: np.ndarray):
        """Add audio frames to buffer (called by audio callback)"""
        with self.lock:
            # Flatten to mono and convert to float32 if needed
            new_data = frames.flatten().astype(np.float32)
            self.buffer = np.concatenate((self.buffer, new_data))
            self.total_frames += len(frames)
    
    def get_chunk(self) -> Optional[np.ndarray]:
        """
        Get a complete audio chunk for transcription
        Returns None if insufficient data available
        """
        with self.lock:
            if len(self.buffer) >= self.chunk_size:
                # Extract chunk using numpy slicing
                chunk = self.buffer[:self.chunk_size].copy()
                self.buffer = self.buffer[self.chunk_size:]
                return chunk
            return None
    
    def get_remaining(self) -> Optional[np.ndarray]:
        """Get any remaining audio in buffer"""
        with self.lock:
            if len(self.buffer) > 0:
                chunk = self.buffer.copy()
                self.buffer = np.array([], dtype=np.float32)
                return chunk
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
    
    def __init__(self, 
                 config: MeetingConfig, 
                 transcriber: Optional[AudioTranscriber] = None,
                 db = None,
                 vector_store = None,
                 summary_agent = None,
                 action_agent = None):
        self.config = config
        self.transcriber = transcriber or AudioTranscriber()
        
        # Injected background dependencies
        self.db = db
        self.vector_store = vector_store
        self.summary_agent = summary_agent
        self.action_agent = action_agent
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.audio_buffer: Optional[AudioBuffer] = None
        self.audio_stream = None
        
        self.is_recording = False
        self.transcription_results: List[dict] = []
        self.participants: List[str] = []
        self.meeting_active = False
        import threading
        self.hard_stop_flag = threading.Event()
        self.stop_event = asyncio.Event()  # For instant stop signaling
        self.background_tasks: List[asyncio.Task] = []
        
        # Timing bookkeeping
        self.joined_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        
    def emit_status(self, state: str, detail: str = ""):
        """Push a state string to the globally preserved singleton manager for UI consumption"""
        bot_manager.push_status({"state": state, "detail": detail})
        
    async def join_meeting(self):
        """
        Main entry point: Join meeting and start audio capture
        
        Returns:
            dict: Meeting session info and transcription results
        """
        self.emit_status("JOINING", "Connecting to session...")
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
            self.joined_at = time.time()  # Record actual join time
            await self._join_meeting_by_platform()
            
            # Step 2: Send chat disclaimer (BEFORE audio starts, as requested)
            await self.send_chat_disclaimer()
            
            # Step 3: Start audio capture
            try:
                self._start_audio_capture()
            except Exception as audio_error:
                print(f"\n[WARNING] Audio capture failed: {audio_error}")
                print("[WARNING] Continuing without audio capture (bot will stay in meeting)")
                print("[WARNING] You can still see the bot in the context, but no transcription will occur")
            
            # Step 4: Monitor meeting, transcribe, and scrape participants
            await self._monitor_meeting()
            
            # Step 5: Cleanup
            return self._finalize_session()
            
        except Exception as e:
            print(f"[ERROR] Meeting bot error: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _launch_browser(self):
        """Launch Playwright browser for a guest join"""
        print("[INFO] Launching browser for guest meeting join...")
        
        playwright = await async_playwright().start()
        
        # Launch browser without persistence for reliability
        self.browser = await playwright.chromium.launch(
            headless=False,
            args=[
                '--use-fake-ui-for-media-stream',
                '--use-fake-device-for-media-stream',
                '--disable-blink-features=AutomationControlled',
                '--autoplay-policy=no-user-gesture-required',
                '--mute-audio',
            ]
        )
        self.context = await self.browser.new_context(
            permissions=['microphone', 'camera'],
            viewport={'width': 1280, 'height': 720}
        )
        self.page = await self.context.new_page()
        print("[SUCCESS] Browser launched (Incognito/Guest Mode)")
    
    async def _minimize_browser(self):
        """Minimize the browser window after joining the meeting"""
        try:
            # Use CDP to minimize the window
            cdp = await self.page.context.new_cdp_session(self.page)
            window_info = await cdp.send("Browser.getWindowForTarget")
            window_id = window_info["windowId"]
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {"windowState": "minimized"}
            })
            print("  [SUCCESS] Browser window minimized")
        except Exception as e:
            # Fallback: move window off-screen
            try:
                await self.page.evaluate("window.moveTo(-10000, -10000)")
                print("  [SUCCESS] Browser window moved off-screen")
            except:
                print(f"  [WARNING] Could not minimize browser: {e}")

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
                print("  [SUCCESS] Clicked 'Join from Browser'")
            except PlaywrightTimeout:
                print("  [WARNING] 'Join from Browser' link not found, may already be on join page")
            
            await asyncio.sleep(2)
            
            # Enter name (required by Zoom)
            name_input = self.page.locator('input[type="text"]#input-for-name, input[placeholder*="name" i]').first
            await name_input.fill("AI Meeting Assistant Bot")
            print("  [SUCCESS] Entered bot name")
            
            # Disable camera if configured
            if self.config.disable_camera:
                try:
                    camera_button = self.page.locator('button[aria-label*="camera" i], button:has-text("Stop Video")')
                    await camera_button.click(timeout=5000)
                    print("  [SUCCESS] Camera disabled")
                except:
                    pass  # Camera may already be off
            
            # Mute microphone if configured
            if self.config.mute_on_join:
                try:
                    mute_button = self.page.locator('button[aria-label*="mute" i], button:has-text("Mute")')
                    await mute_button.click(timeout=5000)
                    print("  [SUCCESS] Microphone muted")
                except:
                    pass
            
            # Click "Join" button
            join_button = self.page.locator('button:has-text("Join")')
            await join_button.click()
            print("  [SUCCESS] Clicked 'Join Meeting'")
            
            await asyncio.sleep(5)
            
            # Check for waiting room
            waiting_room = self.page.locator('text="Waiting for the host to start this meeting"')
            if await waiting_room.count() > 0:
                print("  [WAIT] In waiting room... waiting for host")
            
            self.meeting_active = True
            print("[SUCCESS] Successfully joined Zoom meeting")
            
            # Minimize browser window to keep it out of the way
            await self._minimize_browser()
            
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
                print("  [WARNING] Google account login required!")
                print("  [INFO] Please log in manually in the browser window")
                print("  [WAIT] Waiting for login... (60 seconds)")
                await asyncio.sleep(60)  # Give user time to log in
            
            # Wait explicitly for the guest name input field
            try:
                print("  [WAIT] Waiting for name input field...")
                name_input = self.page.locator('input[placeholder*="name" i], input[aria-label*="name" i]')
                await name_input.first.wait_for(state="visible", timeout=15000)
                await name_input.first.fill(self.config.bot_name)
                print(f"  [SUCCESS] Entered identity: {self.config.bot_name}")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  [INFO] No name field found (might be logged in): {e}")
            
            # Disable camera
            if self.config.disable_camera:
                try:
                    camera_button = self.page.locator('button[aria-label*="camera" i][aria-label*="off" i], div[data-tooltip*="camera" i]')
                    if await camera_button.count() > 0:
                        await camera_button.first.click(timeout=5000)
                        print("  [SUCCESS] Camera disabled")
                except:
                    pass
            
            # Mute microphone
            if self.config.mute_on_join:
                try:
                    mic_button = self.page.locator('button[aria-label*="microphone" i][aria-label*="off" i], div[data-tooltip*="microphone" i]')
                    if await mic_button.count() > 0:
                        await mic_button.first.click(timeout=5000)
                        print("  [SUCCESS] Microphone muted")
                except:
                    pass
            
            await asyncio.sleep(2)
            
            # Click "Join now" or "Ask to join" using explicit waiting
            try:
                print("  [WAIT] Waiting for Join button...")
                join_button = self.page.locator('button:has-text("Join now"), button:has-text("Ask to join")')
                await join_button.first.wait_for(state="visible", timeout=10000)
                await join_button.first.click()
                print("  [SUCCESS] Clicked 'Join' / 'Ask to join'")
            except Exception as e:
                print(f"  [WARNING] Could not click join button: {e}")
                raise
            
            # PROMPT 1: Wait conditions so it does not fail due to loading
            print("  [WAIT] Waiting to be admitted to the meeting...")
            try:
                # Wait for meeting controls to appear (signaling admission)
                controls_locator = self.page.locator('button[aria-label*="Leave call" i], button[aria-label*="Turn off microphone" i], div[data-meeting-code]')
                await controls_locator.first.wait_for(state="visible", timeout=60000)
                self.meeting_active = True
                print("[SUCCESS] Successfully admitted to Google Meet")
            except Exception as e:
                print(f"[ERROR] Failed to confirm admission to Google Meet: {e}")
                raise
            
            # Minimize browser window to keep it out of the way
            await self._minimize_browser()
            
        except Exception as e:
            print(f"❌ Failed to join Google Meet: {e}")
            raise
    
    def _start_audio_capture(self):
        """
        Start capturing audio in real-time.
        Prioritizes VB-Cable (Virtual Audio Device) for unified clean routing, with default fallback.
        """
        print("\n🎤 Initializing audio capture sequence...")
        print(f"   [Debug] Requested Sample Rate: {self.config.sample_rate} Hz")
        print(f"   [Debug] Requested Channels: {self.config.channels}")
        print(f"   [Debug] Max Chunk Duration: {self.config.chunk_duration} seconds")
        
        # Initialize audio buffer
        self.audio_buffer = AudioBuffer(
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            chunk_duration=self.config.chunk_duration
        )
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                # Only print severe errors to avoid console spam on minor drops
                if 'input overflow' in str(status).lower():
                    print(f"  ⚠️  CRITICAL AUDIO DROPS: {status}")
                pass 
            if self.is_recording:
                self.audio_buffer.add_frames(indata.copy())
        
        # Strategy 1: Explicitly hunt for VB-Cable
        print("  🔍 Strategy 1: Attempting to bind to VB-Cable Virtual Audio Device...")
        try:
            devices = sd.query_devices()
            cable_device_idx = None
            
            # Specifically hunt for 'CABLE Output' or 'VB-Audio'
            for i, d in enumerate(devices):
                name = d['name'].lower()
                if d['max_input_channels'] > 0 and ('cable' in name or 'vb-audio' in name):
                    cable_device_idx = i
                    print(f"  [SUCCESS] Found VB-Cable Virtual Device at index {i}: '{d['name']}'")
                    break
            
            if cable_device_idx is None:
                raise ValueError("VB-Cable not found in system devices.")
            
            self.audio_stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                callback=audio_callback,
                blocksize=16384, # Increased massively to prevent input overflow at all costs
                latency='high',  # Force high latency mode to protect buffer
                dtype=np.float32,
                device=cable_device_idx
            )
            self.audio_stream.start()
            self.is_recording = True
            print(f"  [SUCCESS] Audio stream STARTED successfully on: {devices[self.audio_stream.device]['name']}")
            return
            
        except Exception as e:
            print(f"  [ERROR] Audio capture failed. No system audio capture device available: {e}")
            raise RuntimeError("No system audio capture device available")
    
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
        self.background_tasks.append(transcription_task)
        
        # Removed participant scraping loop per user architecture guidelines
        
        # Monitor meeting end
        start_time = time.time()
        max_duration = self.config.duration_minutes * 60
        
        try:
            while not self.stop_event.is_set() and self.meeting_active:
                # Check timeout
                if time.time() - start_time > max_duration:
                    print(f"\n[INFO] Maximum duration ({self.config.duration_minutes} min) reached")
                    break
                
                # Check if meeting ended (platform-specific detection)
                # Use a faster check
                if await self._is_meeting_ended():
                    print("\n[INFO] Meeting ended detected")
                    break
                
                # Sleep in smaller increments to check stop_event frequently
                for _ in range(5):
                    if self.stop_event.is_set():
                        break
                    await asyncio.sleep(1)
                
        finally:
            self.ended_at = time.time()  # Record actual end time
            self.meeting_active = False
            self.is_recording = False
            self.hard_stop_flag.set()
            
            # Wait for transcription to finish, unless hard stopped
            if not self.hard_stop_flag.is_set():
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
        temp_dir = settings.TRANSCRIPTS_DIR        
        temp_dir.mkdir(exist_ok=True)
        
        self.emit_status("TRANSCRIBING", "Recording and transcribing audio in real-time...")
        
        while (self.is_recording or self.meeting_active) and not self.hard_stop_flag.is_set():
            if self.stop_event.is_set() or self.hard_stop_flag.is_set():
                break

            # Get complete audio chunk from buffer
            audio_chunk = self.audio_buffer.get_chunk()
            
            if audio_chunk is not None:
                chunk_count += 1
                print(f"[INFO] Transcribing chunk #{chunk_count}...")
                
                try:
                    # Check if chunk has any actual audio (not just silence)
                    # This prevents Whisper from hallucinating during silences
                    rms = np.sqrt(np.mean(audio_chunk**2))
                    if rms < 0.005: # Silence threshold
                        # print(f"  [WAIT] Skipping silent chunk (RMS: {rms:.5f})")
                        continue

                    # Create temporary WAV file in memory-backed location
                    temp_path = temp_dir / f"chunk_{chunk_count}_{int(time.time())}.wav"
                    self.audio_buffer.save_to_temp_wav(audio_chunk, temp_path)
                    
                    # Transcribe with language lock and hint vocabulary
                    result = self.transcriber.transcribe_audio(
                        temp_path, 
                        language=settings.WHISPER_LANGUAGE,
                        prompt=self.config.prompt_context
                    )
                    
                    # Store transcription result
                    self.transcription_results.append({
                        'chunk_number': chunk_count,
                        'timestamp': datetime.now().isoformat(),
                        'text': result['text'],
                        'duration': result['duration']
                    })
                    
                    # Display transcription
                    print(f"  [SUCCESS] Chunk #{chunk_count}: {result['text'][:100]}...")
                    print()
                    
                    # Clean up temp file
                    temp_path.unlink()
                    
                except Exception as e:
                    print(f"  [ERROR] Transcription error for chunk #{chunk_count}: {e}")
            
            else:
                # No complete chunk yet, wait
                await asyncio.sleep(1)
        
        # Process any remaining audio
        remaining = self.audio_buffer.get_remaining()
        if remaining is not None and len(remaining) > 1000:  # At least 1 second
            print("[INFO] Transcribing final chunk...")
            try:
                temp_path = temp_dir / f"chunk_final_{int(time.time())}.wav"
                self.audio_buffer.save_to_temp_wav(remaining, temp_path)
                result = self.transcriber.transcribe_audio(
                    temp_path,
                    prompt=self.config.prompt_context
                )
                self.transcription_results.append({
                    'chunk_number': chunk_count + 1,
                    'timestamp': datetime.now().isoformat(),
                    'text': result['text'],
                    'duration': result['duration']
                })
                temp_path.unlink()
            except Exception as e:
                print(f"  [ERROR] Final chunk transcription error: {e}")
        
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
    
    async def send_chat_disclaimer(self):
        """Send a professional disclaimer message in the meeting chat"""
        print("[INFO] Sending chat disclaimer...")
        try:
            disclaimer = "SYSTEM: AI Meeting Assistant has joined. This session is being recorded for automated transcription and summary generation."
            
            if self.config.platform.lower() == "zoom":
                # Zoom chat flow
                chat_button = self.page.locator('button[aria-label="Chat"], button[aria-label*="open chat" i]')
                await chat_button.first.click()
                await asyncio.sleep(1)
                
                chat_input = self.page.locator('textarea[placeholder*="Type message" i], .chat-box__input')
                await chat_input.first.fill(disclaimer)
                await self.page.keyboard.press("Enter")
                
            elif self.config.platform.lower() in ["google_meet", "meet"]:
                # Google Meet chat flow
                print("  [WAIT] Waiting to ensure meeting is fully loaded before opening chat...")
                await asyncio.sleep(5)
                
                chat_button = self.page.locator('button[aria-label*="chat with everyone" i], button[aria-label*="chat" i]').first
                try:
                    await chat_button.wait_for(state="visible", timeout=10000)
                    await chat_button.click()
                    print("  [SUCCESS] Opened chat panel")
                    
                    # WAIT for chat panel to expand
                    chat_input = self.page.locator('textarea[name="chatTextInput"], textarea[aria-label*="chat" i], aside textarea').first
                    await chat_input.wait_for(state="visible", timeout=10000)
                    
                    # Focus, fill, and send
                    await chat_input.click()
                    await asyncio.sleep(0.5)
                    await chat_input.fill("")
                    await chat_input.type(disclaimer, delay=20)
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    print("  ✓ Disclaimer sent to chat")
                    
                    # Verification (Prompt 2)
                    await asyncio.sleep(1)
                    sent_msg = self.page.locator(f'text="{disclaimer}"')
                    if await sent_msg.count() > 0:
                        print("  [SUCCESS] Chat message verified in DOM.")
                    else:
                        print("  [WARNING] Chat message sent, but could not verify in DOM.")
                except Exception as e:
                    print(f"  [WARNING] Explicit chat injection failed, trying keyboard generic fallback... ({e})")
                    # Fallback generic injection
                    await self.page.keyboard.press("Tab")
                    await self.page.keyboard.type(disclaimer, delay=30)
                    await self.page.keyboard.press("Enter")
                    print("  [SUCCESS] Disclaimer sent manually via keyboard")
                
        except Exception as e:
            print(f"  [WARNING] Could not send chat disclaimer: {e}")

    async def stop_async(self):
        """Async implementation of stop signaling and Playwright cleanup"""
        print("\n[STOP] Stop signal received. Attempting clean meeting exit...")
        self.meeting_active = False
        self.is_recording = False
        self.stop_event.set() # Trigger immediate loop break
        
        try:
            if self.page and not self.page.is_closed():
                # PROMPT 4: Attempt graceful "Leave" click first
                print("  [WAIT] Clicking Leave Meeting button...")
                if self.config.platform.lower() == "zoom":
                    leave_btn = self.page.locator('button:has-text("Leave"), button[aria-label="Leave"]')
                    if await leave_btn.count() > 0:
                        await leave_btn.first.click(timeout=3000)
                        confirm_leave = self.page.locator('button:has-text("Leave Meeting")')
                        if await confirm_leave.count() > 0:
                            await confirm_leave.first.click(timeout=3000)
                else:
                    leave_btn = self.page.locator('button[aria-label*="Leave call" i]')
                    if await leave_btn.count() > 0:
                        await leave_btn.first.click(timeout=3000)
                
                print("  [SUCCESS] Successfully clicked leave UI")
            
            # Immediately close the browser to avoid lingering windows and loops
            if self.browser:
                await self.browser.close()
                print("  [SUCCESS] Browser forcefully closed for instant termination")
                
        except Exception as e:
            print(f"  [WARNING] Could not click leave button gracefully: {e}")
            
    def stop(self):
        """Signal the bot to stop and leave the meeting immediately"""
        print("\n[STOP] HARD STOP signal received from UI. Terminating immediately...")
        self.hard_stop_flag.set()
        self.stop_event.set()
        self.meeting_active = False
        self.is_recording = False
        
        # Stop audio stream immediately
        if self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                print(f"  [WARNING] Error stopping audio stream: {e}")
                
        # Run the async stop routine in the local event loop safely
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Cancel all background tasks immediately
                for task in self.background_tasks:
                    if not task.done():
                        task.cancel()
                loop.call_soon_threadsafe(lambda: loop.create_task(self.stop_async()))
            else:
                loop.run_until_complete(self.stop_async())
        except Exception as e:
            print(f"  ⚠️ Error scheduling stop_async: {e}")
            
    def _finalize_session(self) -> dict:
        """
        Finalize meeting session and return results
        
        Returns:
            dict: Complete session info including all transcriptions
        """
        self.emit_status("FINALIZING", "Compiling final transcript...")
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
        latest_path = settings.TRANSCRIPTS_DIR / "live_meeting_latest.txt"
        
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(full_transcript)
        with open(latest_path, 'w', encoding='utf-8') as f:
            f.write(full_transcript)
        
        print(f"✅ Full transcript saved: {transcript_path}")
        print(f"📊 Total chunks transcribed: {len(self.transcription_results)}")
        print(f"📝 Total characters: {len(full_transcript)}")
        
        cleaned_transcript = full_transcript
        summary = ""
        action_items = []
        
        # 1. POST_PROCESSING (Clean proper nouns via LLM)
        if self.summary_agent and self.config.prompt_context:
            self.emit_status("POST_PROCESSING", "Correcting proper nouns and phonetics via LLM...")
            cleaned_transcript = self.summary_agent.clean_transcript(full_transcript, self.config.prompt_context)
        
        # 2. GENERATING_SUMMARY (Summarize using Cleaned Transcript)
        if self.summary_agent:
            self.emit_status("GENERATING_SUMMARY", "Analyzing transcript and formatting summary...")
            participants_list = [p.strip() for p in self.config.prompt_context.split(',')] if self.config.prompt_context else []
            ctx = {
                'title': "Live Meeting",
                'date': datetime.now().strftime("%Y-%m-%d"),
                'participants': participants_list
            }
            summary_res = self.summary_agent.generate_summary(cleaned_transcript, meeting_context=ctx)
            summary = summary_res.get('summary', '')

        # 3. EXTRACTING_ACTIONS (Extract tasks from Cleaned Transcript)
        if self.action_agent:
            self.emit_status("EXTRACTING_ACTIONS", "Scanning context for actionable tasks and deadlines...")
            action_items = self.action_agent.extract_action_items(cleaned_transcript)
        
        # 4. ARCHIVING (Push everything to Mongo and Chroma)
        if self.db:
            self.emit_status("ARCHIVING", "Saving full intelligence report to Meeting Archive...")
            meeting_id = str(int(time.time()))
            participants_list = [p.strip() for p in self.config.prompt_context.split(',')] if self.config.prompt_context else []
            
            # Calculate actual duration
            actual_duration = 0
            if self.joined_at and self.ended_at:
                actual_duration = int(self.ended_at - self.joined_at)
            else:
                actual_duration = self.config.duration_minutes * 60
                
            meeting_data = {
                "meeting_id": meeting_id,
                "title": "Live Meeting",
                "date": datetime.now().isoformat(),
                "participants": participants_list,
                "transcript": cleaned_transcript,
                "raw_transcript": full_transcript,
                "summary": summary,
                "duration": actual_duration,
                "meeting_url": self.config.meeting_url,
                "platform": self.config.platform,
                "meeting_type": "live_meeting",
                "is_live_capture": True,
                "joined_at": datetime.fromtimestamp(self.joined_at).isoformat() if self.joined_at else None,
                "ended_at": datetime.fromtimestamp(self.ended_at).isoformat() if self.ended_at else None,
                "linked_account": self.config.linked_account,
                "calendar_event_id": self.config.calendar_event_id,
                "invitees": self.config.invitees
            }
            self.db.save_meeting(meeting_data)
            
            for item in action_items:
                item['meeting_id'] = meeting_id
                self.db.save_action_item(item)
                
            if self.vector_store:
                self.vector_store.add_meeting(
                    meeting_id=meeting_id,
                    transcript=cleaned_transcript,
                    metadata={
                        "title": "Live Meeting",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "participants": ", ".join(participants_list)
                    }
                )
                
        self.emit_status("DONE", "Meeting processed successfully. View results in Meeting Archive.")
        
        return {
            'meeting_url': self.config.meeting_url,
            'platform': self.config.platform,
            'transcript_path': str(transcript_path),
            'chunks': self.transcription_results,
            'full_transcript': full_transcript,
            'cleaned_transcript': cleaned_transcript,
            'summary': summary,
            'action_items': action_items,
            'total_chunks': len(self.transcription_results),
            'participants': self.participants,
            'meeting_id': meeting_id if self.db else None
        }
    
    async def _cleanup(self):
        """Cleanup resources and cancel background tasks silently"""
        # NOISE SUPPRESSION: We use a broad try-except here because Playwright 
        # and asyncio can throw noisy pipe errors during teardown that are safe to ignore.
        try:
            print("\n🧹 Cleaning up session resources...")
            
            # Safely cancel all background tasks
            for task in self.background_tasks:
                try:
                    if not task.done():
                        task.cancel()
                except:
                    pass
            
            if self.background_tasks:
                try:
                    # Wait briefly for tasks to acknowledge cancellation (max 2 seconds)
                    await asyncio.wait(
                        [asyncio.create_task(t) if not t.done() else t for t in self.background_tasks], 
                        timeout=2.0
                    )
                except:
                    pass
            
            # Stop audio capture
            if hasattr(self, 'audio_stream') and self.audio_stream:
                try:
                    self.audio_stream.stop()
                    self.audio_stream.close()
                    print("  ✓ Audio stream closed")
                except:
                    pass
            
            # Close browser violently to avoid background ghosting
            if hasattr(self, 'browser') and self.browser:
                try:
                    await self.browser.close()
                    print("  ✓ Browser explicitly destroyed")
                except:
                    pass
            elif hasattr(self, 'context') and self.context:
                try:
                    # Explicitly ignore any errors during context close as it's the last step
                    await asyncio.wait_for(self.context.close(), timeout=2.0)
                    print("  ✓ Browser context closed")
                except:
                    # Move on silently - browser will be reaped by OS anyway
                    pass
            
            print("✅ Cleanup complete\n")
        except Exception:
            # Broadest possible catch to ensure user never sees teardown errors again
            pass


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
