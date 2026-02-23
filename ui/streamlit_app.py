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

from audio_processing.transcriber import AudioTranscriber
from agents.summary_agent import SummaryAgent
from agents.action_item_agent import ActionItemAgent
from database.mongodb_client import db
from rag.vector_store import VectorStore
from integrations.meeting_bot import join_and_capture_audio, MeetingConfig, MeetingBot
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

@st.cache_resource
def load_models():
    """Load all models (cached)"""
    with st.spinner("Loading AI models... (this may take a minute)"):
        transcriber = AudioTranscriber()
        summary_agent = SummaryAgent()
        action_agent = ActionItemAgent()
        vector_store = VectorStore()
    return transcriber, summary_agent, action_agent, vector_store

def main():
    st.title("🎙️ AI Meeting Assistant")
    st.markdown("Upload audio, get transcripts, summaries, and action items automatically!")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Model info
        with st.expander("🤖 Model Information"):
            st.write(f"**Whisper Model:** {settings.WHISPER_MODEL}")
            st.write(f"**LLM:** {settings.GROQ_MODEL}")
            st.write(f"**Device:** {settings.WHISPER_DEVICE}")
        
        # Database stats
        with st.expander("📊 Database Stats"):
            try:
                stats = db.get_statistics()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("📁 Recordings", stats.get('uploaded_recordings', 0))
                with col2:
                    st.metric("🤖 Live Meetings", stats.get('live_meetings', 0))
                st.metric("Total Action Items", stats.get('total_action_items', 0))
                st.metric("Pending Actions", stats.get('pending_actions', 0))
            except Exception as e:
                st.error(f"Could not load stats: {e}")
                import traceback
                st.code(traceback.format_exc())
        
        st.divider()
        
        # Navigation
        page = st.radio(
            "Navigate",
            ["🎙️ New Meeting", "🤖 Join Live Meeting", "📚 Past Meetings", "✅ Action Items"],
            label_visibility="collapsed"
        )
    
    # Load models
    if st.session_state.transcriber is None:
        try:
            (st.session_state.transcriber, 
             st.session_state.summary_agent,
             st.session_state.action_agent,
             st.session_state.vector_store) = load_models()
        except Exception as e:
            st.error(f"Error loading models: {e}")
            st.stop()
    
    # Route to appropriate page
    if page == "🎙️ New Meeting":
        new_meeting_page()
    elif page == "🤖 Join Live Meeting":
        live_meeting_page()
    elif page == "📚 Past Meetings":
        past_meetings_page()
    elif page == "✅ Action Items":
        action_items_page()

def live_meeting_page():
    """Page for joining live meetings with bot"""
    st.header("🤖 Join Live Meeting")
    st.markdown("Enter a meeting link and the bot will join automatically to capture and transcribe audio in real-time!")
    
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
        **How it works:**
        
        1. 🌐 Bot opens browser
        2. 🎯 Joins meeting as "AI Meeting Assistant Bot"
        3. 🎤 Captures audio in real-time
        4. 📝 Transcribes every 30 seconds
        5. 💾 Saves complete transcript
        
        **Requirements:**
        - Stereo Mix or VB-CABLE enabled
        - Browser will open (don't close it!)
        - For Google Meet: May need to log in
        
        **The bot will:**
        - ✅ Turn off camera
        - ✅ Mute microphone
        - ✅ Be visible to participants
        """)
    
    st.divider()
    
    # Audio device selection
    st.markdown("### 🎤 Audio Device Setup")
    
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
    with st.expander("⚙️ **IMPORTANT: Enable Stereo Mix First!**", expanded=True):
        st.markdown("""
        ### 🔴 Steps to Enable Stereo Mix (Windows):
        
        **If you're getting audio errors, follow these steps:**
        
        1. **Right-click** the 🔊 **speaker icon** in your taskbar (bottom-right corner)
        2. Click **"Sounds"** or **"Open Sound settings"** → **"Sound Control Panel"**
        3. Go to **"Recording"** tab
        4. **Right-click** in the empty space
        5. Check ✅ **"Show Disabled Devices"**
        6. You should now see **"Stereo Mix"** in the list
        7. **Right-click** on **"Stereo Mix"** → Click **"Enable"**
        8. **Right-click** on **"Stereo Mix"** again → Click **"Set as Default Device"**
        9. Click **"OK"** to save
        10. **Refresh this page** and select Stereo Mix again
        
        ---
        
        ### 🎤 **Quick Test Option:**
        
        **Don't want to setup Stereo Mix right now?**
        - Select any **"Microphone"** device from the dropdown above
        - It will work for testing (but won't capture meeting audio well)
        - Stereo Mix is needed to capture what meeting participants are saying
        
        ---
        
        ### 📦 **Alternative: Install VB-CABLE**
        
        If Stereo Mix doesn't work:
        - Download: https://vb-audio.com/Cable/
        - Install, restart, then set "CABLE Output" as recording device
        """)
    
    st.divider()
    
    # Additional info
    with st.expander("ℹ️ About the Meeting Bot"):
        st.markdown("""
        **What the bot does:**
        - Joins meeting in browser window  
        - Appears as "AI Meeting Assistant Bot"
        - Captures meeting audio via system
        - Transcribes with Whisper AI
        
        **Important:**
        - ✅ Bot is visible to all participants
        - ✅ Always get consent before recording
        """)
    
    # Validate device before allowing join
    device_ready = AUDIO_AVAILABLE and st.session_state.get('selected_device_index') is not None
    
    # Audio setup check
    with st.expander("🔊 Audio Troubleshooting"):
        st.caption("Having audio issues?")
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
    
    # Join button
    if meeting_url:
        if url_valid and device_ready:
            if st.button("🚀 Join Meeting Now", type="primary", use_container_width=True):
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

def join_live_meeting(url, platform, duration, title, participants_str):
    """Join live meeting with bot and process results"""
    meeting_id = str(uuid.uuid4())[:8]
    
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
        headless=True,  # Run in background
        bot_name="AI Meeting Assistant Bot"
    )
    
    try:
        st.info(f"🤖 Starting fully automated bot...")
        
        # Create a container for live updates
        status_container = st.empty()
        progress_bar = st.progress(0)
        
        with status_container.container():
            st.markdown("### 🔄 Bot Status")
            st.write("🤖 Bot starting in background (invisible mode)...")
            if device_index is not None:
                st.write(f"🎤 Audio device: Index {device_index}")
            st.success(f"""
            **✅ Bot is completely automated!**
            - Running in background (invisible)
            - Auto-joining as "{config.bot_name}"
            - Camera/mic off automatically
            - Real-time transcription active
            - Duration: {duration} minutes
            
            **No actions needed - fully automatic!**
            """)
        
        # Run meeting bot in a separate thread to avoid asyncio conflicts
        import asyncio
        import queue as queue_module
        import time
        
        result_queue = queue_module.Queue()
        bot_instance = [None]  # Use list to store reference for stop control
        
        def run_bot():
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Create bot and run (config already created in main thread)
                bot = MeetingBot(config)
                bot_instance[0] = bot  # Store reference
                result = loop.run_until_complete(bot.join_meeting())
                result_queue.put(('success', result))
            except Exception as e:
                result_queue.put(('error', e))
            finally:
                loop.close()
        
        # Start bot thread
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
        # Add stop button placeholder
        stop_placeholder = st.empty()
        
        # Wait for completion with timeout
        max_wait = (duration * 60) + 120  # Duration + 2 min buffer
        start_time = time.time()
        
        while bot_thread.is_alive() and (time.time() - start_time) < max_wait:
            elapsed = int(time.time() - start_time)
            progress = min(int((elapsed / (duration * 60)) * 100), 99)
            progress_bar.progress(progress)
            
            # Show stop button
            with stop_placeholder:
                if st.button("🛑 Stop Bot & Leave Meeting", key=f"stop_bot_{elapsed}"):
                    if bot_instance[0]:
                        bot_instance[0].stop()
                        st.warning("🛑 Stopping bot... Please wait.")
                        time.sleep(3)
                        break
            
            time.sleep(1)
        
        # Get result
        try:
            status, result = result_queue.get(timeout=5)
        except Exception as e:
            st.warning("⚠️ Meeting bot stopped unexpectedly")
            st.info("If the bot appeared in the meeting briefly, this is normal - it may have joined successfully but closed early.")
            return
        
        if status == 'error':
            raise result
        
        progress_bar.progress(100)
        
        st.success("✅ Meeting bot has left the meeting!")
        
        # Get results
        transcript_text = result['full_transcript']
        
        # Display transcript
        st.markdown("---")
        st.markdown("### 📝 Meeting Transcript")
        with st.expander("View Full Transcript", expanded=True):
            st.text_area("Transcript", transcript_text, height=300, key="live_transcript")
            
            # Show chunks info
            st.caption(f"Transcribed in {result['total_chunks']} chunks")
        
        # Generate summary
        st.markdown("---")
        with st.spinner("📊 Generating summary..."):
            participants_list = [p.strip() for p in participants_str.split(',')] if participants_str else []
            summary_result = st.session_state.summary_agent.generate_summary(
                transcript_text,
                meeting_context={
                    'title': title or "Live Meeting",
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'participants': participants_list
                }
            )
            summary = summary_result['summary']
        
        st.markdown("### 📋 Meeting Summary")
        with st.expander("View Summary", expanded=True):
            st.markdown(summary)
        
        # Extract action items
        with st.spinner("✅ Extracting action items..."):
            action_items = st.session_state.action_agent.extract_action_items(transcript_text)
        
        if action_items:
            st.markdown("### 📌 Action Items")
            with st.expander(f"View {len(action_items)} Action Items", expanded=True):
                for i, item in enumerate(action_items, 1):
                    priority_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                    emoji = priority_color.get(item.get('priority', 'medium'), '⚪')
                    
                    st.markdown(f"**{i}. {emoji} {item['task']}**")
                    col1, col2, col3 = st.columns(3)
                    col1.caption(f"👤 Owner: {item.get('owner', 'Unassigned')}")
                    col2.caption(f"📅 Deadline: {item.get('deadline', 'Not specified')}")
                    col3.caption(f"⚡ Priority: {item.get('priority', 'medium')}")
                    st.divider()
        
        # Save to database
        with st.spinner("💾 Saving to database..."):
            meeting_data = {
                "meeting_id": meeting_id,
                "title": title or "Live Meeting",
                "date": datetime.now().isoformat(),
                "participants": participants_list if participants_str else [],
                "transcript": transcript_text,
                "summary": summary,
                "duration": duration * 60,  # Convert to seconds
                "meeting_url": url,
                "platform": platform,
                "meeting_type": "live_meeting",  # Track meeting type
                "is_live_capture": True
            }
            db.save_meeting(meeting_data)
            
            # Save action items
            for item in action_items:
                item['meeting_id'] = meeting_id
                db.save_action_item(item)
            
            # Save to vector store
            st.session_state.vector_store.add_meeting(
                meeting_id=meeting_id,
                transcript=transcript_text,
                metadata={
                    "title": title or "Live Meeting",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "participants": participants_str or "Unknown"
                }
            )
        
        st.success("🎉 Meeting processed and saved successfully!")
        st.balloons()
        
        # Show file location
        st.info(f"📁 Transcript saved to: `{result['transcript_path']}`")
        
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

def new_meeting_page():
    """Page for uploading and processing new meetings"""
    st.header("Upload New Meeting")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Meeting details
        meeting_title = st.text_input("Meeting Title", placeholder="e.g., Q4 Planning Meeting")
        participants = st.text_input("Participants (comma-separated)", 
                                    placeholder="John, Sarah, Mike")
        
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
        if st.button("🚀 Process Meeting", type="primary", use_container_width=True):
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
        with st.spinner("🎙️ Transcribing audio... (this may take a few minutes)"):
            transcription = st.session_state.transcriber.transcribe_audio(str(audio_path))
            transcript_text = transcription['text']
        
        st.success("✅ Transcription complete!")
        
        # Display transcript
        with st.expander("📝 View Transcript", expanded=True):
            st.text_area("Transcript", transcript_text, height=200)
        
        # Step 2: Generate summary
        with st.spinner("📊 Generating summary..."):
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
        
        st.success("✅ Summary generated!")
        
        # Display summary
        with st.expander("📋 Meeting Summary", expanded=True):
            st.markdown(summary)
        
        # Step 3: Extract action items
        with st.spinner("✅ Extracting action items..."):
            action_items = st.session_state.action_agent.extract_action_items(transcript_text)
        
        if action_items:
            st.success(f"✅ Found {len(action_items)} action items!")
            
            with st.expander("📌 Action Items", expanded=True):
                for i, item in enumerate(action_items, 1):
                    priority_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                    emoji = priority_color.get(item.get('priority', 'medium'), '⚪')
                    
                    st.markdown(f"**{i}. {emoji} {item['task']}**")
                    col1, col2, col3 = st.columns(3)
                    col1.caption(f"👤 Owner: {item.get('owner', 'Unassigned')}")
                    col2.caption(f"📅 Deadline: {item.get('deadline', 'Not specified')}")
                    col3.caption(f"⚡ Priority: {item.get('priority', 'medium')}")
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
        
    except Exception as e:
        st.error(f"Error processing meeting: {e}")
        import traceback
        st.code(traceback.format_exc())

def past_meetings_page():
    """View past meetings and ask questions"""
    st.header("📚 Past Meetings")
    
    try:
        meetings = db.get_all_meetings(limit=50)
        
        if not meetings:
            st.info("No meetings found. Upload your first meeting!")
            return
        
        # Search and filter
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("🔍 Search meetings", placeholder="Search by title, participants...")
        with col2:
            filter_type = st.selectbox("Filter", ["All", "Live Meetings", "Recordings"])
        
        # Apply filters
        filtered_meetings = meetings
        if search_query:
            filtered_meetings = [m for m in filtered_meetings if 
                       search_query.lower() in m.get('title', '').lower() or
                       search_query.lower() in str(m.get('participants', [])).lower()]
        
        if filter_type == "Live Meetings":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'live_meeting']
        elif filter_type == "Recordings":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'uploaded_recording']
        
        st.write(f"Found {len(filtered_meetings)} meeting(s)")
        
        # Display meetings
        for meeting in filtered_meetings:
            # Meeting type badge
            meeting_type = meeting.get('meeting_type', 'uploaded_recording')
            if meeting_type == 'live_meeting':
                type_badge = "🤖 Live Meeting"
            else:
                type_badge = "📁 Uploaded Recording"
            
            # Expander title
            title_text = f"{type_badge} | {meeting.get('title', 'Untitled')} - {meeting.get('date', '')[:10]}"
            
            with st.expander(title_text, expanded=False):
                # Header row with delete button
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**📅 Date:** {meeting.get('date', 'Unknown')[:19]}")
                    st.markdown(f"**👥 Participants:** {', '.join(meeting.get('participants', ['No participants'])) or 'Not specified'}")
                    st.markdown(f"**⏱️ Duration:** {meeting.get('duration', 0):.1f} seconds")
                    
                    # Show meeting link for live meetings
                    if meeting_type == 'live_meeting' and meeting.get('meeting_url'):
                        st.markdown(f"**🔗 Meeting Link:** [{meeting.get('platform', 'Link')}]({meeting['meeting_url']})")
                
                with col2:
                    if st.button("🗑️ Delete", key=f"del_{meeting['meeting_id']}", type="secondary"):
                        with st.spinner("Deleting..."):
                            db.delete_meeting(meeting['meeting_id'])
                            st.session_state.vector_store.delete_meeting(meeting['meeting_id'])
                            st.success("Deleted!")
                            st.rerun()
                
                st.divider()
                
                # Summary Section
                with st.container():
                    st.markdown("### 📝 Summary")
                    summary_text = meeting.get('summary', 'No summary available')
                    st.markdown(summary_text)
                
                st.divider()
                
                # Action Items Section
                with st.container():
                    st.markdown("### ✅ Action Items")
                    actions = db.get_action_items(meeting_id=meeting['meeting_id'])
                    
                    if actions:
                        for idx, item in enumerate(actions, 1):
                            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                            emoji = priority_emoji.get(item.get('priority', 'medium'), '⚪')
                            status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}
                            status = status_emoji.get(item.get('status', 'pending'), '⏳')
                            
                            st.markdown(f"{idx}. {emoji} {status} **{item['task']}** - {item.get('owner', 'Unassigned')} (Deadline: {item.get('deadline', 'N/A')})")
                    else:
                        st.info("No action items for this meeting")
                
                st.divider()
                
                # Transcript Section
                with st.container():
                    st.markdown("### 📄 Full Transcript")
                    transcript_text = meeting.get('transcript', 'No transcript available')
                    st.text_area("", transcript_text, height=200, key=f"transcript_{meeting['meeting_id']}", label_visibility="collapsed")
                
                st.divider()
                
                # Ask Questions Section
                with st.container():
                    st.markdown("### 💬 Ask Questions About This Meeting")
                    st.caption("Ask specific questions about this meeting or general knowledge questions")
                    
                    question = st.text_input(
                        "Your question", 
                        placeholder="What was discussed? What decisions were made?",
                        key=f"q_{meeting['meeting_id']}"
                    )
                    
                    if question:
                        with st.spinner("🔍 Thinking..."):
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
        st.error(f"Error loading meetings: {e}")
        import traceback
        st.code(traceback.format_exc())

def action_items_page():
    """View and manage action items"""
    st.header("✅ Action Items")
    
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
