"""
Streamlit UI for AI Meeting Assistant
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import uuid
# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from integrations.bot_manager import bot_manager
from audio_processing.transcriber import AudioTranscriber
from agents.summary_agent import SummaryAgent
from agents.action_item_agent import ActionItemAgent
from agents.context_agent import ContextAgent
from database.mongodb_client import db
from rag.vector_store import VectorStore
from integrations.meeting_bot import join_and_capture_audio, MeetingConfig, MeetingBot
from integrations.email_sender import EmailSender
import config.settings as settings
import threading

try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False

# Page configuration
st.set_page_config(
    page_title="AI Meeting Assistant",
    page_icon="🎙️",
    layout="wide"
)

# Initialize session state
if 'transcriber' not in st.session_state:
    st.session_state.transcriber = None
if 'summary_agent' not in st.session_state:
    st.session_state.summary_agent = None
if 'action_agent' not in st.session_state:
    st.session_state.action_agent = None
if 'vector_store' not in st.session_state:
    st.session_state.vector_store = None
if 'context_agent' not in st.session_state:
    st.session_state.context_agent = None
if 'email_sender' not in st.session_state:
    st.session_state.email_sender = None

@st.cache_resource
def load_models():
    """Load all models (cached)"""
    with st.spinner("Loading AI models... (this may take a minute)"):
        transcriber = AudioTranscriber()
        summary_agent = SummaryAgent()
        action_agent = ActionItemAgent()
        vector_store = VectorStore()
        context_agent = ContextAgent(vector_store=vector_store)
        email_sender = EmailSender()
    return transcriber, summary_agent, action_agent, vector_store, context_agent, email_sender

def main():
    st.title("Meeting Intelligence Assistant")
    st.markdown("Automated transcription, summary generation, and cross-meeting intelligence.")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        
        # Model info
        with st.expander("Model Configuration"):
            st.write(f"**Whisper Model:** {settings.WHISPER_MODEL}")
            st.write(f"**LLM:** {settings.GROQ_MODEL}")
            st.write(f"**Device:** {settings.WHISPER_DEVICE}")
        
        # Database stats
        with st.expander("Analytics"):
            try:
                stats = db.get_statistics()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Recordings", stats.get('uploaded_recordings', 0))
                with col2:
                    st.metric("Live Sessions", stats.get('live_meetings', 0))
                st.metric("Total Action Items", stats.get('total_action_items', 0))
                st.metric("Pending Actions", stats.get('pending_actions', 0))
            except Exception as e:
                st.error(f"Could not load stats: {e}")
                import traceback
                st.code(traceback.format_exc())
        
        st.divider()
        
        # Navigation
        page = st.radio(
            "Navigation",
            ["New Recording", "Join Session", "Global Intelligence", "Meeting Archive", "Action Tracker"],
            label_visibility="collapsed"
        )
    
    # Load models
    if st.session_state.transcriber is None:
        try:
            (st.session_state.transcriber, 
             st.session_state.summary_agent,
             st.session_state.action_agent,
             st.session_state.vector_store,
             st.session_state.context_agent,
             st.session_state.email_sender) = load_models()
        except Exception as e:
            st.error(f"Error loading models: {e}")
            st.stop()
    
    # Route to appropriate page
    if page == "New Recording":
        new_meeting_page()
    elif page == "Join Session":
        live_meeting_page()
    elif page == "Global Intelligence":
        global_intelligence_page()
    elif page == "Meeting Archive":
        past_meetings_page()
    elif page == "Action Tracker":
        action_items_page()

def live_meeting_page():
    """Page for joining live meetings with bot"""
    st.header("Join Live Session")
    st.markdown("Enter a meeting link to initiate automated audio capture and real-time transcription.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Meeting platform selection
        platform = st.selectbox(
            "Meeting Platform",
            ["Google Meet", "Zoom"],
            help="Select the platform for your meeting"
        )
        
        # Meeting URL input
        meeting_url = st.text_input(
            "Meeting URL",
            placeholder="https://meet.google.com/abc-defg-hij or https://zoom.us/j/123456789",
            help="Paste the full meeting link here"
        )
        
        # Meeting details
        col_a, col_b = st.columns(2)
        with col_a:
            meeting_title = st.text_input(
                "Meeting Title (optional)",
                placeholder="e.g., Team Standup"
            )
        with col_b:
            duration = st.number_input(
                "Max Duration (minutes)",
                min_value=1,
                max_value=180,
                value=30,
                help="Bot will automatically leave after this time"
            )
        
        participants = st.text_input(
            "Expected Participants (optional)",
            placeholder="John, Sarah, Mike"
        )
    
    with col2:
        st.info("""
        System Operations:
        
        1. Browser initialization
        2. Session entry as "AI Meeting Assistant Bot"
        3. Real-time audio stream capture
        4. Progressive transcription (30s intervals)
        5. Archive generation
        
        Requirements:
        - System Audio Loopback enabled
        - Maintain active browser session
        
        Bot Protocols:
        - Camera: Disabled
        - Microphone: Muted
        - Visibility: Active Participant
        """)
    
    st.divider()
    
    # Audio device selection
    st.markdown("### Audio Configuration")
    
    if AUDIO_AVAILABLE:
        try:
            devices = sd.query_devices()
            input_devices = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    input_devices.append({
                        'index': i,
                        'name': device['name']
                    })
            
            if input_devices:
                device_options = [f"[{d['index']}] {d['name']}" for d in input_devices]
                
                # Try to find Stereo Mix or loopback device
                default_idx = 0
                for i, d in enumerate(input_devices):
                    device_name_lower = d['name'].lower()
                    if any(keyword in device_name_lower for keyword in ['stereo mix', 'cable', 'loopback', 'blackhole']):
                        default_idx = i
                        st.success(f"✅ Found virtual audio device: {d['name']}")
                        break
                
                selected_device_str = st.selectbox(
                    "Select Audio Input Device",
                    device_options,
                    index=default_idx,
                    help="Select your virtual audio cable or Stereo Mix device. For testing, you can also use your Microphone.",
                    key="audio_device_selector"
                )
                
                # Extract and store device index
                device_index = int(selected_device_str.split('[')[1].split(']')[0])
                st.session_state['selected_device_index'] = device_index
                st.session_state['selected_device_str'] = selected_device_str
                
                # Show device-specific help
                if 'Stereo Mix' in selected_device_str:
                    st.warning("⚠️ **Stereo Mix selected!** Make sure it's ENABLED first (see instructions below)")
                elif 'Microphone' in selected_device_str:
                    st.info("💡 **Microphone selected.** This works but won't capture meeting audio well. Use Stereo Mix for better results.")
                
                st.info(f"💡 Using device index: {device_index}")
            else:
                st.error("❌ No audio input devices found!")
                st.session_state['selected_device_index'] = None
        except Exception as e:
            st.error(f"❌ Error loading audio devices: {e}")
            st.session_state['selected_device_index'] = None
    else:
        st.error("❌ sounddevice not installed. Run: pip install sounddevice")
        st.session_state['selected_device_index'] = None
    
    # Setup instructions
    with st.expander("System Configuration: Audio Loopback", expanded=True):
        st.markdown("""
        ### Enable Stereo Mix (Windows Instruction):
        
        If audio signal is not detected, please verify the following:
        
        1. Access **Sound Control Panel** via Taskbar or Settings.
        2. Navigate to the **Recording** tab.
        3. Right-click and ensure **Show Disabled Devices** is enabled.
        4. Locate **Stereo Mix**, right-click, and select **Enable**.
        5. Set as **Default Device**.
        6. Refresh this application and re-select the device.
        
        ### Alternative Configuration:
        
        **Microphone Input:**
        - You may select a physical Microphone for testing purposes.
        - Note: This will not accurately capture remote participant audio.
        
        **Virtual Audio Cable:**
        - Install VB-CABLE (vb-audio.com) for professional routing.
        """)
    
    st.divider()
    
    # Additional info
    with st.expander("Assistant Protocols"):
        st.markdown("""
        Assistant Operations:
        - Joins via secure browser instance.
        - Appears as "AI Meeting Assistant Bot".
        - Captures system-wide audio signal.
        - Processes via Whisper AI.
        
        Privacy Note:
        - Ensure all participants are informed of automated recording.
        """)
    
    # Validate device before allowing join
    device_ready = AUDIO_AVAILABLE and st.session_state.get('selected_device_index') is not None
    
    # Audio setup check
    with st.expander("Audio Troubleshooting"):
        st.caption("Common resolution steps")
        st.markdown("""
        **Test your audio device in terminal:**
        ```bash
        python integrations/audio_device_helper.py
        ```
        
        **If you get "Invalid device" error:**
        - Your selected device is disabled in Windows
        - Follow the "Enable Stereo Mix" steps above
        - OR select a Microphone device for quick testing
        
        **Files with detailed help:**
        - `ENABLE_STEREO_MIX.md` - Step-by-step Stereo Mix guide
        - `MEETING_BOT_GUIDE.md` - Complete documentation
        """)
    
    # Validate URL
    url_valid = meeting_url and (
        meeting_url.startswith("https://meet.google.com/") or
        meeting_url.startswith("https://zoom.us/") or
        "zoom.us" in meeting_url
    )
    
    # Check if device is ready
    device_ready = AUDIO_AVAILABLE and st.session_state.get('selected_device_index') is not None
    
    # Reconnect to active session if running
    if bot_manager.is_running():
        st.info("🔄 Active session detected in background. Reconnecting UI...")
        join_live_meeting(None, None, None, None, None, reconnect=True)
        return
        
    # Join button
    if meeting_url:
        if url_valid and device_ready:
            if st.button("Initiate Session", type="primary", use_container_width=True):
                # Convert platform name
                platform_code = "google_meet" if platform == "Google Meet" else "zoom"
                
                # Join meeting (no warnings needed - fully automated)
                join_live_meeting(meeting_url, platform_code, duration, meeting_title, participants)
        elif not device_ready:
            st.error("❌ Please enable and select Stereo Mix in the audio device selector above.")
            st.info("💡 After enabling Stereo Mix in Windows settings, refresh this page.")
        else:
            st.error("❌ Invalid meeting URL. Please check the format.")
    else:
        st.info("👆 Enter a meeting URL above to start")
        
    # Check for latest transcript
    import os
    TRANSCRIPT_PATH = settings.TRANSCRIPTS_DIR / "live_meeting_latest.txt"
    if os.path.exists(TRANSCRIPT_PATH):
        st.markdown("---")
        st.markdown("### Latest Meeting Transcript (Recovered)")
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            st.text_area("Transcript", f.read(), height=300)

def join_live_meeting(url, platform, duration, title, participants_str, reconnect=False):
    """Join live meeting with bot and process results or reconnect to active one"""
    meeting_id = str(uuid.uuid4())[:8]
    
    # Placeholders for dynamic UI elements
    status_container = st.empty()
    stop_placeholder = st.empty()
    timer_placeholder = st.empty()
    
    try:
        if not reconnect:
            # Get audio device selection BEFORE any threading
            # This avoids session state access issues
            device_index = None
            if AUDIO_AVAILABLE and 'selected_device_index' in st.session_state:
                device_index = st.session_state['selected_device_index']
            
            # Create configuration BEFORE threading to avoid session state conflicts
            config = MeetingConfig(
                meeting_url=url,
                platform=platform,
                duration_minutes=duration,
                audio_device=device_index,
                headless=True,
                bot_name="MeetAI",
                prompt_context=participants_str  # Pass names down to fix spelling mistakes in transcription!
            )
            
            st.info("Initializing automated assistant...")
            
            with status_container.container():
                st.markdown("### Assistant Status")
                st.write("Connecting to session...")
                if device_index is not None:
                    st.write(f"🎤 Audio device: Index {device_index}")
            
            # Run meeting bot in a separate thread via bot_manager
            import asyncio
            import time
            
            # Extract dependencies from Streamlit session context BEFORE going multi-threaded
            # Streamlit throws ScriptRunContext errors if 'st.session_state' is accessed directly inside a Thread
            vs_ref = st.session_state.vector_store
            sa_ref = st.session_state.summary_agent
            aa_ref = st.session_state.action_agent
            
            def run_bot():
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Injected backend dependencies
                    bot = MeetingBot(
                        config=config, 
                        db=db,
                        vector_store=vs_ref,
                        summary_agent=sa_ref,
                        action_agent=aa_ref
                    )
                    bot_manager.bot_instance = bot  # Store reference
                    result = loop.run_until_complete(bot.join_meeting())
                    bot_manager.result_queue.put(('success', result))
                except Exception as e:
                    bot_manager.result_queue.put(('error', e))
                finally:
                    loop.close()
            
            # Start bot thread
            bot_manager.start_bot(run_bot)
            st.session_state.has_active_meeting = True
            
            # Phase 1: Wait for bot to actually join the meeting
            join_wait_start = time.time()
            join_timeout = 120  # 2 minutes to join
            bot_joined = False
            
            while bot_manager.is_running() and (time.time() - join_wait_start) < join_timeout:
                # Check if bot has joined
                if bot_manager.bot_instance and getattr(bot_manager.bot_instance, 'meeting_active', False):
                    bot_joined = True
                    break
                
                # Check if bot errored out before joining
                if not bot_manager.result_queue.empty():
                    break
                
                time.sleep(0.5)
            
            if not bot_joined:
                # Bot didn't join - check for errors
                try:
                    status, result = bot_manager.result_queue.get(timeout=2)
                    if status == 'error':
                        raise result
                except Exception as e:
                    if not isinstance(e, Exception) or str(e) == '':
                        st.error("❌ Bot could not join the meeting within the timeout period.")
                    else:
                        raise
                return
        else:
            # Reconnect block
            import time
            max_wait = 180 # default
            if bot_manager.bot_instance:
                duration = bot_manager.bot_instance.config.duration_minutes
                max_wait = (duration * 60) + 120
                
        # UI status block
        status_box = st.status("Reconnecting to MeetingBot Pipeline..." if reconnect else "Initializing MeetingBot Pipeline...", expanded=True)
        
        # Phase 2: Bot has joined! Show the active meeting UI
        join_time = time.time()
        
        with status_container.container():
            st.success(f"""
            Session Active:
            - Connected as "{settings.BOT_NAME}"
            - Protocols: Camera/Mic disabled, audio muted
            - Intelligent transcription active
            """)
        
        # Wait for completion with live timer and stop button
        max_wait = (duration * 60) + 120  # Duration + 2 min buffer
        
        while bot_manager.is_running() and (time.time() - join_time) < max_wait:
            elapsed_seconds = int(time.time() - join_time)
            hours = elapsed_seconds // 3600
            minutes = (elapsed_seconds % 3600) // 60
            seconds = elapsed_seconds % 60
            
            if hours > 0:
                timer_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                timer_str = f"{minutes:02d}:{seconds:02d}"
            
            # Show live timer
            timer_placeholder.markdown(
                f"### Session Duration: **{timer_str}**"
            )
            
            # Poll status queue dynamically
            while bot_manager.status_queue and not bot_manager.status_queue.empty():
                evt = bot_manager.status_queue.get()
                state = evt.get("state", "UNKNOWN")
                detail = evt.get("detail", "")
                
                if state == "DONE":
                    status_box.update(label=detail, state="complete")
                    status_box.write(f"✅ **{state}**: {detail}")
                elif state == "ERROR":
                    status_box.update(label=detail, state="error")
                else:
                    status_box.update(label=f"[{state}] {detail}", state="running")
                    status_box.write(f"🔄 **{state}**: {detail}")
            
            # Show stop button
            with stop_placeholder:
                if st.button("Terminate Session", key=f"stop_bot_{elapsed_seconds}", type="primary", use_container_width=True):
                        bot_manager.stop_bot()
                        timer_placeholder.markdown(f"### Finalizing after **{timer_str}**")
                        st.warning("🛑 Terminating assistant... Finalizing intelligence report in background.")
                        # Let the bot finish its cleanup gracefully
                        pass
            
            # Check stop_event indirectly by checking thread or results
            if not bot_manager.is_running():
                break

            time.sleep(1)
            
        # Drain remaining status queue messages sequentially before final display
        while bot_manager.status_queue and not bot_manager.status_queue.empty():
            evt = bot_manager.status_queue.get()
            state = evt.get("state", "UNKNOWN")
            detail = evt.get("detail", "")
            if state == "DONE":
                status_box.update(label=detail, state="complete")
                status_box.write(f"✅ **{state}**: {detail}")
            else:
                status_box.write(f"🔄 **{state}**: {detail}")
        
        # Clear dynamic elements
        stop_placeholder.empty()
        
        # Final timer display
        final_elapsed = int(time.time() - join_time)
        final_h = final_elapsed // 3600
        final_m = (final_elapsed % 3600) // 60
        final_s = final_elapsed % 60
        if final_h > 0:
            final_timer = f"{final_h:02d}:{final_m:02d}:{final_s:02d}"
        else:
            final_timer = f"{final_m:02d}:{final_s:02d}"
        timer_placeholder.markdown(f"### Final Duration: **{final_timer}**")
        
        # Get result with a much longer timeout
        try:
            status, result = bot_manager.result_queue.get(timeout=60) # Increased from 5s to 60s
        except Exception as e:
            st.warning("⚠️ Background process detached from UI (This happens on manual terminate).")
            import os
            TRANSCRIPT_PATH = settings.TRANSCRIPTS_DIR / "live_meeting_latest.txt"
            if os.path.exists(TRANSCRIPT_PATH):
                with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
                    transcript_text = f.read()
                st.success("✅ Recovered latest transcript from disk!")
                st.markdown("---")
                st.markdown("### Session Transcript")
                with st.expander("View Transcript", expanded=True):
                    st.text_area("Transcript", transcript_text, height=300, key="recovered_live_transcript")
            else:
                st.info("No transcript file found yet. Wait a few seconds and refresh.")
            return
        
        if status == 'error':
            raise result
        
        st.success("✅ Meeting bot has left the meeting!")
        
        # Display extracted results directly from the background payload
        transcript_text = result.get('full_transcript', '')
        cleaned_transcript = result.get('cleaned_transcript', '')
        summary = result.get('summary', 'No summary generated.')
        action_items = result.get('action_items', [])
        
        st.info("The intelligence extraction has completed perfectly. Please review the reports below and switch to the 'Meeting Archive' tab whenever you're ready.")
        
        # Display transcripts
        st.markdown("---")
        st.markdown("### Session Transcript")
        tab1, tab2 = st.tabs(["Cleaned Transcript (Proper Nouns Corrected)", "Raw Transcript"])
        with tab1:
            st.text_area("Clean Transcript", cleaned_transcript, height=300, key="clean_transcript")
        with tab2:
            st.text_area("Raw", transcript_text, height=300, key="raw_transcript")
            st.caption(f"Transcribed in {result.get('total_chunks', 0)} chunks")
        
        # Display Analytical Summary and Actions
        st.markdown("---")
        with st.expander("Analytical Summary", expanded=True):
            st.markdown(summary)
            
        if action_items:
            st.markdown("### Action Items")
            with st.expander(f"Identified Tasks ({len(action_items)})", expanded=True):
                for i, item in enumerate(action_items, 1):
                    confidence = str(item.get('confidence', 'medium')).upper()
                    st.markdown(f"**{i}. {item.get('task', 'Unknown task')}**")
                    col1, col2, col3 = st.columns(3)
                    col1.caption(f"Assignee: {item.get('assignee_name', 'Unassigned')}")
                    col2.caption(f"Deadline: {item.get('deadline', 'Not specified')}")
                    col3.caption(f"Confidence: {confidence}")
                    if item.get('evidence'):
                        st.caption(f"🔍 *Evidence: \"{item.get('evidence')}\"*")
                    st.divider()

        # 5. COMMUNICATION DISPATCH
        st.markdown("---")
        st.markdown("### Communication Dispatch")
        st.info("Generation complete. Please review the reports below to verify and dispatch to your team.")
        dispatch_summary(summary, action_items, title or "Live Meeting", participants_str, transcript_text)
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.markdown("**Troubleshooting:**")
        st.markdown("1. Ensure VB-CABLE is installed and configured")
        st.markdown("2. Run: `python integrations/audio_device_helper.py`")
        st.markdown("3. Check that the meeting URL is correct")
        st.markdown("4. For Google Meet, you may need to log in manually when prompted")
        
        with st.expander("View Error Details"):
            import traceback
            st.code(traceback.format_exc())

def dispatch_summary(summary, action_items, title, initial_participants, transcript=""):
    """Component for verifying, editing, and sending meeting intelligence"""
    
    st.markdown("---")
    st.markdown("### Protocol Review & Dispatch")
    st.markdown("Review the intelligence reports and verify recipients before final transmission.")

    # 1. Content Review
    with st.expander("Content Review (Edit if necessary)", expanded=False):
        edited_title = st.text_input("Report Title", value=title)
        edited_summary = st.text_area("Analytical Summary", value=summary, height=300)
        
        # Proper formatting for transcript (cleaner join)
        formatted_transcript = transcript.replace("[Chunk", "\n\n[Section")
        edited_transcript = st.text_area("Full Transcript", value=formatted_transcript, height=300)

    # 2. Recipient Verification
    if st.session_state.email_sender and st.session_state.email_sender.enabled:
        with st.expander("Recipient Entry", expanded=True):
            st.markdown("Enter recipient emails to distribute the intelligence report.")
            
            verified_emails = []
            
            # Default Host email if set
            host_email = settings.SENDER_EMAIL or ""
            
            email_input = st.text_input(
                "Host / Primary Email", 
                value=host_email,
                placeholder="host@example.com"
            )
            if email_input:
                verified_emails.append(email_input.strip())
            
            other_emails = st.text_input(
                "Additional Recipients", 
                placeholder="colleague@example.com, manager@example.com",
                help="Comma-separated list of additional emails"
            )
            if other_emails:
                for e in other_emails.split(','):
                    if e.strip():
                        verified_emails.append(e.strip())
            
            # Send button
            if st.button("Finalize & Distribute Report", type="primary", use_container_width=True):
                # Unique emails only
                verified_emails = list(set(verified_emails))
                
                if not verified_emails:
                    st.warning("Please specify at least one verified recipient.")
                else:
                    with st.spinner("Transmitting encrypted intelligence..."):
                        # Use EDITED content for the email
                        success = st.session_state.email_sender.send_meeting_summary(
                            verified_emails,
                            edited_summary,  # Use edited version
                            action_items,
                            edited_title     # Use edited version
                        )
                        if success:
                            st.success(f"Intelligence report successfully transmitted to {len(verified_emails)} recipients.")
                        else:
                            st.error("Transmission failure. Please verify SMTP configuration.")
    else:
        st.info("Email communication is disabled. Please configure SMTP credentials in .env to enable distribution.")

def new_meeting_page():
    """Page for uploading and processing new meetings"""
    st.header("Process Recording")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Meeting details
        meeting_title = st.text_input("Session Title", placeholder="e.g., Strategic Planning")
        participants = st.text_input("Participants (comma separated)", 
                                    placeholder="Jane Doe, John Smith")
        
        # File upload
        audio_file = st.file_uploader(
            "Upload Audio File",
            type=['mp3', 'wav', 'm4a', 'ogg', 'flac', 'mp4'],
            help=f"Max size: {settings.MAX_AUDIO_SIZE_MB}MB"
        )
    
    with col2:
        st.info("""
        **Supported formats:**
        - MP3, WAV, M4A
        - OGG, FLAC
        - MP4 (audio)
        
        **Tips:**
        - Clear audio = better results
        - 5-60 minutes optimal
        - Avoid background noise
        """)
    
    # Process button
    if audio_file and meeting_title:
        if st.button("Analyze Recording", type="primary", use_container_width=True):
            process_meeting(audio_file, meeting_title, participants)
    elif audio_file and not meeting_title:
        st.warning("Please enter a meeting title")

def process_meeting(audio_file, title, participants_str):
    """Process uploaded meeting"""
    meeting_id = str(uuid.uuid4())[:8]
    
    try:
        # Save audio file
        audio_path = settings.MEETINGS_DIR / f"{meeting_id}_{audio_file.name}"
        with open(audio_path, "wb") as f:
            f.write(audio_file.getbuffer())
        
        st.info(f"Processing meeting: {title}")
        
        # Step 1: Transcribe
        with st.spinner("Executing transcription..."):
            transcription = st.session_state.transcriber.transcribe_audio(str(audio_path))
            transcript_text = transcription['text']
        
        st.success("Transcription complete")
        
        # Display transcript
        with st.expander("Transcription Record", expanded=True):
            st.text_area("Transcript", transcript_text, height=200)
        
        # Step 2: Generate summary
        with st.spinner("Generating summary..."):
            participants_list = [p.strip() for p in participants_str.split(',')] if participants_str else []
            summary_result = st.session_state.summary_agent.generate_summary(
                transcript_text,
                meeting_context={
                    'title': title,
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'participants': participants_list
                }
            )
            summary = summary_result['summary']
        
        st.success("Summary generated")
        
        # Display summary
        with st.expander("Analytical Summary", expanded=True):
            st.markdown(summary)
        
        # Step 3: Extract action items
        with st.spinner("Extracting action items..."):
            action_items = st.session_state.action_agent.extract_action_items(transcript_text)
        
        if action_items:
            st.success(f"Identified {len(action_items)} tasks")
            
            with st.expander("Action Items", expanded=True):
                for i, item in enumerate(action_items, 1):
                    st.markdown(f"**{i}. {item['task']}**")
                    col1, col2, col3 = st.columns(3)
                    col1.caption(f"Owner: {item.get('owner', 'Unassigned')}")
                    col2.caption(f"Deadline: {item.get('deadline', 'Not specified')}")
                    col3.caption(f"Priority: {item.get('priority', 'medium').upper()}")
                    st.divider()
        else:
            st.info("No action items found in this meeting")
        
        # Step 4: Save to databases
        with st.spinner("💾 Saving to database..."):
            # Save to MongoDB
            meeting_data = {
                "meeting_id": meeting_id,
                "title": title,
                "date": datetime.now().isoformat(),
                "participants": participants_list if participants_str else [],
                "transcript": transcript_text,
                "summary": summary,
                "duration": transcription.get('duration', 0),
                "audio_file": str(audio_path),
                "meeting_type": "uploaded_recording",  # Track meeting type
                "meeting_url": None  # No URL for uploaded recordings
            }
            db.save_meeting(meeting_data)
            
            # Save action items
            for item in action_items:
                item['meeting_id'] = meeting_id
                db.save_action_item(item)
            
            # Save to vector store for RAG
            st.session_state.vector_store.add_meeting(
                meeting_id=meeting_id,
                transcript=transcript_text,
                metadata={
                    "title": title,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "participants": participants_str
                }
            )
        
        st.success("🎉 Meeting processed and saved successfully!")
        st.balloons()
        
        # Dispatch Center
        st.markdown("---")
        st.markdown("### Communication Dispatch")
        st.markdown("Verify details and distribute the meeting intelligence report.")
        
        dispatch_summary(summary, action_items, title, participants_list, transcript_text)
        
    except Exception as e:
        st.error(f"Error processing meeting: {e}")
        import traceback
        st.code(traceback.format_exc())

def past_meetings_page():
    """View past meetings and ask questions"""
    st.header("Meeting Archive")
    
    # Premium Dark Aurora / Glassmorphism overriding styles for the Archive page
    st.markdown("""
        <style>
        /* Targeting Expander blocks for a deeper glass look */
        [data-testid="stExpander"] {
            background: rgba(30, 35, 45, 0.4);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        }
        /* Make inner text glow slightly */
        h3 {
            background: -webkit-linear-gradient(45deg, #4da6ff, #99c2ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .transcript-line {
            font-family: 'Inter', sans-serif;
            color: #d1d5db;
            line-height: 1.6;
            padding-bottom: 8px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    try:
        meetings = db.get_all_meetings(limit=50)
        
        if not meetings:
            st.info("No meetings found. Upload your first meeting!")
            return
        
        # Search and filter
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("Search archives", placeholder="Search by title, participants...", label_visibility="collapsed")
        with col2:
            filter_type = st.selectbox("Category", ["All", "Live Sessions", "Recordings"], label_visibility="collapsed")
        
        # Apply filters
        filtered_meetings = meetings
        if search_query:
            filtered_meetings = [m for m in filtered_meetings if 
                       search_query.lower() in m.get('title', '').lower() or
                       search_query.lower() in str(m.get('participants', [])).lower()]
        
        if filter_type == "Live Sessions":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'live_meeting']
        elif filter_type == "Recordings":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'uploaded_recording']
        
        st.caption(f"Archived Sessions: {len(filtered_meetings)}")
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Display meetings
        for meeting in filtered_meetings:
            meeting_type = meeting.get('meeting_type', 'uploaded_recording')
            type_badge = "Live Session" if meeting_type == 'live_meeting' else "Recording"
            title_text = f"🎙️ {meeting.get('title', 'Untitled')} | {meeting.get('date', '')[:10]}"
            
            with st.expander(title_text, expanded=False):
                # Header row with meta info and delete button
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**📅 Date:** {meeting.get('date', 'Unknown')[:19]}  |  **👥 Team:** {', '.join(meeting.get('participants', ['No participants'])) or 'Not specified'}  |  **⏱️ Length:** {meeting.get('duration', 0):.1f}s")
                with col2:
                    if st.button("🗑️ Delete", key=f"del_{meeting['meeting_id']}", type="secondary", use_container_width=True):
                        with st.spinner("Removing record..."):
                            db.delete_meeting(meeting['meeting_id'])
                            st.session_state.vector_store.delete_meeting(meeting['meeting_id'])
                            st.rerun()
                
                st.divider()
                
                # 1. Cleaned Transcript Layout FIRST (Auto-Scrolling Box via st.container height)
                st.markdown("### Cleaned Transcript")
                st.caption("Proper nouns corrected & grammatically structured.")
                clean_t = meeting.get('transcript', 'No cleaned transcript available (Old meeting format).')
                
                # Use a strictly defined height container to simulate auto-scrolling
                with st.container(height=250, border=True):
                    # We render this as simple markdown to retain structural paragraphing
                    st.markdown(f"<div class='transcript-line'>{clean_t}</div>", unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                col_sum, col_act = st.columns([1, 1])
                
                # 2. Summary Block
                with col_sum:
                    st.markdown("### Analytical Summary")
                    with st.container(border=True):
                        st.markdown(meeting.get('summary', 'No summary generated.'))
                
                # 3. Action Items Block
                with col_act:
                    st.markdown("### Action Items")
                    with st.container(border=True):
                        actions = db.get_action_items(meeting_id=meeting['meeting_id'])
                        if actions:
                            for idx, item in enumerate(actions, 1):
                                priority = item.get('priority', 'medium').upper()
                                assignee = item.get('assignee_name', 'Unassigned')
                                confidence = str(item.get('confidence', 'medium')).upper()
                                
                                st.markdown(f"**{idx}. {item['task']}**")
                                st.caption(f"👤 {assignee} | 🎯 Confidence: {confidence}")
                        else:
                            st.info("No direct action items identified.")
                
                # 4. Hidden Raw Transcript
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("🛠️ View Audio-Chunk Raw Transcript (Debug)"):
                    raw_text = meeting.get('raw_transcript', meeting.get('transcript', 'Unavailable.'))
                    st.text_area("Raw Stream Output", raw_text, height=150, key=f"raw_transcript_{meeting['meeting_id']}", label_visibility="collapsed")
                    
                st.divider()
                
                # Ask Questions Section
                with st.container():
                    st.markdown("### Session Intelligence")
                    question = st.text_input(
                        "Ask the LLM specifically about this meeting's context:", 
                        placeholder="e.g. 'What was the final decision on the marketing budget?'",
                        key=f"q_{meeting['meeting_id']}"
                    )
                    
                    if question:
                        with st.spinner("Analyzing..."):
                            try:
                                # Build context with meeting metadata AND transcript
                                meeting_context = f"""Meeting Title: {meeting.get('title', 'Untitled')}
Date: {meeting.get('date', 'Unknown')[:10]}
Participants: {', '.join(meeting.get('participants', ['Not specified']))}
Duration: {meeting.get('duration', 0):.1f} seconds

TRANSCRIPT:
{meeting.get('transcript', '')}"""
                                
                                # Generate answer with full context
                                answer = st.session_state.summary_agent.answer_question(
                                    transcript=meeting_context,
                                    question=question
                                )
                                
                                st.markdown("**Answer:**")
                                st.markdown(answer)
                                
                            except Exception as e:
                                st.error(f"Error: {e}")
        
    except Exception as e:
        st.error(f"Error loading meeting archives: {e}")

def global_intelligence_page():
    """Page for cross-meeting intelligence and RAG chat"""
    st.header("Global Intelligence")
    st.markdown("Query the collective knowledge from all archived meeting sessions.")
    
    # Statistics row
    stats = st.session_state.context_agent.vector_store.get_stats()
    st.caption(f"Archived Knowledge: {stats.get('total_chunks', 0)} analytical units across meetings.")
    
    st.divider()
    
    # Main chat interface
    st.markdown("### Inquiry Terminal")
    query = st.text_input(
        "Enter your query", 
        placeholder="e.g., What were the recurring budget themes in March?",
        help="The system will retrieve relevant context from all past sessions to provide an answer."
    )
    
    if query:
        with st.spinner("Aggregating intelligence and generating response..."):
            try:
                # Get answer from context agent
                answer = st.session_state.context_agent.answer_global_question(query)
                
                # Display answer in a professional container
                st.markdown("#### Analytical Response")
                st.info(answer)
                
                # Show source references
                with st.expander("Intelligence Sources"):
                    sources = st.session_state.context_agent.search_meetings(query, n_results=3)
                    if sources:
                        for idx, source in enumerate(sources, 1):
                            st.markdown(f"**Source {idx}:** {source['metadata'].get('title', 'Unknown Meeting')} ({source['metadata'].get('date', 'N/A')})")
                            st.caption(source['content'])
                            st.divider()
                    else:
                        st.write("No direct source units identified.")
                        
            except Exception as e:
                st.error(f"Inquiry error: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    st.divider()
    st.caption("Note: Accuracy depends on the volume and clarity of archived transcripts.")

def action_items_page():
    """View and manage action items"""
    st.header("Action Tracker")
    
    try:
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Status", ["All", "pending", "completed", "in_progress"])
        with col2:
            owner_filter = st.text_input("Owner", placeholder="Filter by owner...")
        
        # Get action items
        status = None if status_filter == "All" else status_filter
        all_items = db.get_action_items(status=status)
        
        if owner_filter:
            all_items = [item for item in all_items if 
                        owner_filter.lower() in item.get('owner', '').lower()]
        
        if not all_items:
            st.info("No action items found")
            return
        
        # Display items
        st.write(f"Found {len(all_items)} action item(s)")
        
        for item in all_items:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                emoji = priority_emoji.get(item.get('priority', 'medium'), '⚪')
                st.markdown(f"**{emoji} {item['task']}**")
            
            with col2:
                st.caption(f"👤 {item.get('owner', 'Unassigned')}")
            
            with col3:
                st.caption(f"📅 {item.get('deadline', 'N/A')}")
            
            with col4:
                current_status = item.get('status', 'pending')
                new_status = st.selectbox(
                    "Status",
                    ["pending", "in_progress", "completed"],
                    index=["pending", "in_progress", "completed"].index(current_status),
                    key=f"status_{item['_id']}",
                    label_visibility="collapsed"
                )
                
                if new_status != current_status:
                    db.update_action_item_status(item['_id'], new_status)
                    st.rerun()
            
            st.divider()
        
    except Exception as e:
        st.error(f"Error loading action items: {e}")

if __name__ == "__main__":
    main()
