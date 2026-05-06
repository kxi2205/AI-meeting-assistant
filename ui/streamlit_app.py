"""
AI Meeting Assistant UI
"""
import streamlit as st
import sys
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import uuid

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from integrations.recipient_resolver import RecipientResolver
from integrations.google_auth import auth_manager
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
from utils.deadline_parser import get_closest_deadline_warning, parse_deadline
from utils.assignee_resolver import resolve_assignee_email
from integrations.calendar_reminder import create_reminder_event

try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False

# Page configuration
st.set_page_config(
    page_title="AI Meeting Assistant",
    page_icon="AI",
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
if 'recipient_resolver' not in st.session_state:
    st.session_state.recipient_resolver = None

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
        recipient_resolver = RecipientResolver()
    return transcriber, summary_agent, action_agent, vector_store, context_agent, email_sender, recipient_resolver

def main():
    st.title("AI Meeting Assistant")
    st.markdown("Automated transcription, summary generation, and cross-meeting intelligence.")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        
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
        
        # Closest Deadline Warning Card
        try:
            deadline_warning = get_closest_deadline_warning(db)
            if deadline_warning:
                urgency = deadline_warning['urgency']
                label = deadline_warning['label']
                task = deadline_warning['task']
                assignee = deadline_warning['assignee']
                
                warning_text = f"**{label}**\n\n"
                warning_text += f"Task: {task}\n\n"
                warning_text += f"Assignee: {assignee}"
                
                if urgency == 'overdue':
                    st.error(warning_text)
                elif urgency in ('due_today', 'due_tomorrow'):
                    st.warning(warning_text)
                else:
                    st.info(warning_text)
        except Exception as e:
            # Silently skip — deadline warning is non-critical
            print(f"[WARNING] Deadline warning card error: {e}")
        
        # Profile
        with st.expander("Profile", expanded=False):
            accounts = db.get_connected_accounts()
            account_emails = [acc['email'] for acc in accounts]
            
            if accounts:
                st.write("**Connected Google Accounts:**")
                for email in account_emails:
                    st.caption(f"Connected: {email}")
                    if st.button("Disconnect", key=f"del_{email}", help="Remove this account"):
                        if db.delete_connected_account(email):
                            st.success("Disconnected")
                            time.sleep(1)
                            st.rerun()
                
                # Active Account Selection
                selected_account = st.selectbox(
                    "Active Calendar Account",
                    options=account_emails,
                    index=0 if 'active_google_account' not in st.session_state else account_emails.index(st.session_state.active_google_account) if st.session_state.active_google_account in account_emails else 0
                )
                st.session_state.active_google_account = selected_account
            else:
                st.write("No accounts connected.")
                st.session_state.active_google_account = None
                
            st.divider()
            
            if st.button("Connect Google Account", use_container_width=True):
                with st.spinner("Waiting for authentication in browser..."):
                    connected_email = auth_manager.connect_new_account()
                    if connected_email:
                        st.success(f"Connected: {connected_email}")
                        st.session_state.active_google_account = connected_email
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Authentication failed or was cancelled.")

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
             st.session_state.email_sender,
             st.session_state.recipient_resolver) = load_models()
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
    
    # 1. Check for persistent meeting report view
    if 'last_meeting_result' in st.session_state and st.session_state.last_meeting_result:
        if st.button("Start New Session", type="secondary"):
            st.session_state.last_meeting_result = None
            st.rerun()
        display_meeting_report(st.session_state.last_meeting_result)
        return

    # 2. Reconnect to active session if running
    if bot_manager.is_running():
        st.info("Active session detected in background. Reconnecting UI...")
        
        # Load history so the UI isn't blank
        with st.expander("Session History", expanded=False):
            history = bot_manager.get_missed_status_history()
            for evt in history:
                state = evt.get("state", "UNKNOWN")
                detail = evt.get("detail", "")
                st.write(f"**{state}**: {detail}")
        
        # Emergency reset if the regular terminate fails
        if st.button("Emergency Reset (Use if Terminate fails)", type="secondary", use_container_width=True):
            bot_manager.force_reset()
            st.rerun()
            
        join_live_meeting(None, None, None, None, None, reconnect=True)
        return

    # 3. Audio Device Detection and Manual Override
    if AUDIO_AVAILABLE:
        with st.sidebar.expander("Audio Configuration", expanded=False):
            try:
                devices = sd.query_devices()
                input_devices = []
                for i, d in enumerate(devices):
                    if d['max_input_channels'] > 0:
                        name = d['name']
                        # Filter out common mic/headset keywords for safety
                        if any(k in name.lower() for k in ['mic', 'headset', 'bluetooth', 'hands-free', 'handsfree']):
                            continue
                        input_devices.append({'index': i, 'name': name})
                
                device_names = [f"[{d['index']}] {d['name']}" for d in input_devices]
                
                # Auto-selection logic (if not already selected)
                if 'selected_device_index' not in st.session_state or st.session_state.get('selected_device_index') is None:
                    candidates = []
                    for keyword in ['cable', 'stereo mix', 'loopback', 'blackhole', 'monitor']:
                        candidates.extend([d['index'] for d in input_devices if keyword in d['name'].lower()])
                    
                    if candidates:
                        st.session_state['selected_device_index'] = candidates[0]
                
                # UI Selector
                current_idx = st.session_state.get('selected_device_index')
                default_idx = 0
                if current_idx is not None:
                    try:
                        default_idx = [d['index'] for d in input_devices].index(current_idx)
                    except ValueError:
                        default_idx = 0
                
                if device_names:
                    selected_label = st.selectbox(
                        "Loopback Device",
                        options=device_names,
                        index=default_idx,
                        help="Select your virtual audio device (Stereo Mix or VB-Cable). Microphones are hidden for privacy."
                    )
                    st.session_state['selected_device_index'] = int(selected_label.split(']')[0][1:])
                else:
                    st.warning("No loopback devices detected. Please ensure Stereo Mix or VB-Cable is enabled in Windows Sound Settings.")
                    if st.button("Refresh Audio Devices"):
                        st.rerun()
                
            except Exception as e:
                st.error(f"Audio Error: {e}")
    else:
        st.sidebar.error("sounddevice not installed. Audio capture unavailable.")

    device_ready = AUDIO_AVAILABLE and st.session_state.get('selected_device_index') is not None
    
    tab_calendar, tab_manual = st.tabs(["Calendar Mode", "Manual Mode"])
    
    with tab_calendar:
        _render_calendar_mode(device_ready)
        
    with tab_manual:
        _render_manual_mode(device_ready)

def verify_audio_capture():
    """Smart Audio Fallback Strategy: test amplitude to ensure loopback works"""
    if not AUDIO_AVAILABLE or 'audio_candidates' not in st.session_state or not st.session_state['audio_candidates']:
        return None, False
        
    candidates = st.session_state['audio_candidates']
    default_out_idx = sd.default.device[1]
    
    fs = 16000
    t = np.linspace(0, 0.2, int(fs * 0.2), False)
    beep = 0.01 * np.sin(2 * np.pi * 440 * t)  # Very quiet test sound
    
    for idx in candidates:
        try:
            rec = sd.playrec(beep, samplerate=fs, channels=1, input_device=idx, output_device=default_out_idx)
            sd.wait()
            if np.max(np.abs(rec)) > 0.001:  # Audio detected!
                switched = (idx != st.session_state.get('selected_device_index'))
                st.session_state['selected_device_index'] = idx
                return idx, switched
        except Exception:
            continue
    return None, False

def _render_calendar_mode(device_ready):
    """Render the Calendar Mode UI for joining sessions"""
    active_account = st.session_state.get('active_google_account')
    
    if not active_account:
        st.info("To use Calendar Mode, please connect and select a Google Account in the **Profile** sidebar menu.")
        return
        
    st.markdown(f"**Fetching upcoming Google Meet events for:** `{active_account}`")
    
    with st.spinner("Fetching calendar..."):
        events = auth_manager.get_upcoming_events(active_account)
        
    if not events:
        st.info("No upcoming meetings with Google Meet links found in the next 24 hours.")
        return
        
    # Format options for selectbox
    event_options = {}
    for ev in events:
        try:
            # Parse ISO date string properly
            start_dt = datetime.fromisoformat(ev['start_time'].replace('Z', '+00:00'))
            # Format to local display time nicely
            time_str = start_dt.strftime("%I:%M %p")
        except:
            time_str = ev['start_time']
        
        label = f"{time_str} - {ev['title']}"
        event_options[label] = ev
        
    selected_label = st.selectbox("Select Meeting", list(event_options.keys()))
    selected_event = event_options[selected_label]
    
    st.write(f"**Link:** {selected_event['meet_link']}")
    st.write(f"**Attendees:** {len(selected_event['attendees'])} invited")
    if selected_event['attendees']:
        with st.expander("View attendees"):
            with st.container(height=250):
                full_lines = []
                for att in selected_event['attendees']:
                    name = att.get('name', '')
                    email = att.get('email', '')
                    if name and email and name != email:
                        full_lines.append(f"* {name} — [{email}](mailto:{email})")
                    elif email:
                        full_lines.append(f"* [{email}](mailto:{email})")
                    else:
                        full_lines.append(f"* {name}")
                st.markdown("\n".join(full_lines))
    
    duration = st.number_input(
        "Max Duration (minutes)",
        min_value=1, max_value=180, value=60,
        key="calendar_duration",
        help="Bot will automatically leave after this time as a safety measure"
    )
    
    st.divider()
    
    if st.button("Initiate Session", type="primary", use_container_width=True, key="calendar_join_btn"):
        # Use session state to be 100% sure we don't lose the user's duration setting
        final_duration = st.session_state.get("calendar_duration", 60)
        join_live_meeting(
            url=selected_event['meet_link'],
            platform="google_meet",
            duration=final_duration,
            title=selected_event['title'],
            participants_str=None, # We pass structured invitees instead
            reconnect=False,
            calendar_event_id=selected_event['id'],
            linked_account=active_account,
            invitees=selected_event['attendees']
        )

def _render_manual_mode(device_ready):
    """Render the Manual Mode UI for joining sessions"""
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
            value=60,
            help="Bot will automatically leave after this time as a safety measure"
        )
    
    participants = st.text_input(
        "Expected Participants (optional)",
        placeholder="John, Sarah, Mike"
    )
    
    st.divider()
    
    # Validate URL
    url_valid = meeting_url and (
        meeting_url.startswith("https://meet.google.com/") or
        meeting_url.startswith("https://zoom.us/") or
        "zoom.us" in meeting_url
    )
    
    # Join button
    if meeting_url:
        if url_valid:
            if st.button("Initiate Session", type="primary", use_container_width=True):
                # Convert platform name
                platform_code = "google_meet" if platform == "Google Meet" else "zoom"
                
                # Join meeting (no warnings needed - fully automated)
                join_live_meeting(meeting_url, platform_code, duration, meeting_title, participants)
        else:
            st.error("Invalid meeting URL. Please check the format.")
    else:
        st.info("Enter a meeting URL above to start")

def join_live_meeting(url, platform, duration, title, participants_str, reconnect=False, calendar_event_id=None, linked_account=None, invitees=None):
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
                title=title,
                duration_minutes=duration,
                audio_device=device_index,
                headless=True,
                bot_name="MeetAI",
                prompt_context=participants_str,
                linked_account=linked_account,
                calendar_event_id=calendar_event_id,
                invitees=invitees
            )
            
            st.info("Initializing automated assistant...")
            
            with status_container.container():
                st.markdown("### Assistant Status")
                st.write("Connecting to session...")
                if device_index is not None:
                    st.write(f"Audio device: Index {device_index}")
            
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
                    result["title"]=title
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
                        st.error("Bot could not join the meeting within the timeout period.")
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
        if 'meeting_join_time' not in st.session_state:
            st.session_state.meeting_join_time = time.time()
        join_time = st.session_state.meeting_join_time
        
        with status_container.container():
            st.success(f"""
            Session Active:
            - Connected as "{settings.BOT_NAME}"
            - Protocols: Camera/Mic disabled, audio muted
            - Intelligent transcription active
            """)
        
        # Wait for completion with live timer and stop button
        max_wait = (duration * 60) + 120  # Duration + 2 min buffer
        
        # Show stop button ONCE outside the loop to avoid duplicate key errors
        with stop_placeholder:
            if st.button("Terminate Session", key="stable_terminate_btn", type="primary", use_container_width=True):
                bot_manager.stop_bot()
                timer_placeholder.markdown(f"### Finalizing...")
                st.warning("Terminating assistant...")
        
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
                    status_box.write(f"**{state}**: {detail}")
                elif state == "ERROR":
                    status_box.update(label=detail, state="error")
                elif state == "FINALIZING":
                    status_box.update(label=f"{detail}", state="running")
                    status_box.write(f"**{state}**: {detail}")
                else:
                    status_box.update(label=f"[{state}] {detail}", state="running")
                    status_box.write(f"**{state}**: {detail}")
            
            # Check stop_event indirectly by checking thread or results
            if not bot_manager.is_running():
                break

            time.sleep(1)
            
        # Clear the terminate button after meeting ends
        stop_placeholder.empty()
        
        # Drain remaining status queue messages sequentially before final display
        while bot_manager.status_queue and not bot_manager.status_queue.empty():
            evt = bot_manager.status_queue.get()
            state = evt.get("state", "UNKNOWN")
            detail = evt.get("detail", "")
            if state == "DONE":
                status_box.update(label=detail, state="complete")
                status_box.write(f"**{state}**: {detail}")
            else:
                status_box.write(f"**{state}**: {detail}")
        
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
            # Clear join time after meeting completes
            if 'meeting_join_time' in st.session_state:
                del st.session_state.meeting_join_time
        except Exception as e:
            st.warning("Background process detached from UI (This happens on manual terminate).")
            import os
            TRANSCRIPT_PATH = settings.TRANSCRIPTS_DIR / "live_meeting_latest.txt"
            if os.path.exists(TRANSCRIPT_PATH):
                with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
                    transcript_text = f.read()
                st.success("Recovered latest transcript from disk!")
                st.markdown("---")
                st.markdown("### Session Transcript")
                with st.expander("View Transcript", expanded=True):
                    st.text_area("Transcript", transcript_text, height=300, key="recovered_live_transcript")
            else:
                st.info("No transcript file found yet. Wait a few seconds and refresh.")
            return
        
        if status == 'error':
            raise result
        
        st.success("Meeting bot has left the meeting!")
        
        # Store in session state for persistence and show report
        st.session_state.last_meeting_result = result
        display_meeting_report(result)
        return
        
    except Exception as e:
        st.error(f"Error during meeting processing: {e}")
        with st.expander("View Error Details"):
            import traceback
            st.code(traceback.format_exc())

def display_meeting_report(result):
    """Standalone component to display meeting results with persistence"""
    # Display extracted results directly from the background payload
    transcript_text = result.get('full_transcript', '')
    cleaned_transcript = result.get('cleaned_transcript', '')
    summary = result.get('summary', 'No summary generated.')
    action_items = result.get('action_items', [])
    participants_str = result.get('participants_str', 'Detected Attendees')
    title = result.get('title', 'Live Meeting')
    
    st.info("The intelligence extraction has completed perfectly. Please review the reports below and switch to the 'Meeting Archive' tab whenever you're ready.")
    
    # Display transcripts
    st.markdown("---")
    st.markdown("### Session Transcript")
    tab1, tab2 = st.tabs(["Cleaned Transcript", "Raw Transcript"])
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
                    st.caption(f"Evidence: \"{item.get('evidence')}\"")
                st.divider()

    # 5. COMMUNICATION DISPATCH
    st.markdown("---")
    st.markdown("### Communication Dispatch")
    st.info("Generation complete. Please review the reports below to verify and dispatch to your team.")
    dispatch_summary(
        summary, 
        action_items, 
        title, 
        participants_str, 
        transcript_text,
        meeting_id=result.get('meeting_id'),
        meeting_url=result.get('meeting_url'),
        start_time=None 
    )

def dispatch_summary(summary, action_items, title, initial_participants, transcript="", meeting_id=None, meeting_url=None, start_time=None):
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
            
            # Fetch already resolved emails or calendar invitees if this meeting exists in DB
            resolved_mapping = {}
            calendar_invitees = []
            m_data = None
            if meeting_id:
                m_data = db.get_meeting(meeting_id)
                if m_data:
                    resolved_mapping = m_data.get('resolved_emails', {})
                    calendar_invitees = m_data.get('invitees', [])
            
            # Add debug logs as requested
            print(f"DEBUG Email Modal: Meeting ID: {meeting_id}")
            print(f"DEBUG Email Modal: Found m_data: {bool(m_data)}")
            print(f"DEBUG Email Modal: Found calendar_invitees: {len(calendar_invitees) if calendar_invitees else 0}")
            
            # Recipient Data Preparation
            email_data = []
            unresolved_info = []
            
            # 0. Priority: Calendar Invitees from DB
            if calendar_invitees:
                print(f"DEBUG Email Modal: Loading {len(calendar_invitees)} recipient emails from stored invitees")
                for att in calendar_invitees:
                    email_data.append({
                        "Display Name": att.get('name', ''),
                        "Email": att.get('email', ''),
                        "Source": att.get('source', 'Google Calendar')
                    })
            
            # 1. Automatic Resolution with Caching (NEW)
            if not email_data and meeting_url:
                # Check if we already have resolved recipients in DB for this meeting
                if meeting_id:
                    m_data = db.get_meeting(meeting_id)
                    if m_data and m_data.get('resolved_recipients'):
                        print(f"DEBUG: Using cached recipients from DB for meeting {meeting_id}")
                        for r in m_data['resolved_recipients']:
                            email_data.append({
                                "Display Name": r['name'],
                                "Email": r['email'],
                                "Source": f"{r['source']} (Cached)"
                            })
                        if m_data.get('unresolved_participants'):
                            for u in m_data['unresolved_participants']:
                                unresolved_info.append(f"{u['name']} ({u.get('source', 'Unknown')} - Cached)")
                
                # Only resolve if no cached data was found
                if not email_data:
                    print(f"DEBUG: No cache found. Starting recipient resolution for {meeting_url}")
                    with st.spinner("Resolving recipients from integrated sources..."):
                        resolution = st.session_state.recipient_resolver.resolve_all(
                            meeting_url, 
                            participants=initial_participants,
                            start_time=start_time
                        )
                        
                        print(f"DEBUG: Resolution source: {resolution.get('resolved_source', 'Unknown')}")
                        print(f"DEBUG: Resolved {len(resolution['resolved'])} recipients, {len(resolution['unresolved'])} unresolved")
                        
                        for r in resolution['resolved']:
                            email_data.append({
                                "Display Name": r['name'],
                                "Email": r['email'],
                                "Source": r['source']
                            })
                        
                        for u in resolution['unresolved']:
                            unresolved_info.append(f"{u['name']} ({u['source']})")
                        
                        # Save freshly resolved results back to DB if meeting exists
                        if meeting_id and (resolution['resolved'] or resolution['unresolved']):
                            print(f"DEBUG: Saving resolved results to DB for meeting {meeting_id}")
                            db.update_meeting_recipients(
                                meeting_id, 
                                resolution['resolved'], 
                                resolution['unresolved']
                            )
            
            # 2. Database resolved recipients (Legacy Fallback)
            if not email_data and resolved_mapping:
                # Handle legacy mapping format (simple dict)
                if isinstance(resolved_mapping, dict):
                    email_data = [{"Display Name": k, "Email": v, "Source": "Stored Mapping"} for k, v in resolved_mapping.items()]
                else:
                    # Handle new structured format if it exists
                    email_data = [{"Display Name": r['name'], "Email": r['email'], "Source": r['source']} for r in resolved_mapping]
            
            # 3. Fallback for no resolution
            if not email_data:
                print("DEBUG Email Modal: Fallback to manual mode triggered")
                st.info("No participant emails were automatically detected. Please enter them manually.")
                participants = []
                if isinstance(initial_participants, list):
                    participants = initial_participants
                elif isinstance(initial_participants, str):
                    participants = [p.strip() for p in initial_participants.split(',') if p.strip()]
                
                email_data = [{"Display Name": p, "Email": "", "Source": "Manual Entry"} for p in participants]
                if not email_data:
                    email_data = [{"Display Name": "Recipient", "Email": "", "Source": "Manual Entry"}]
            
            # Display unresolved participants separately
            if unresolved_info:
                with st.expander("Unresolved Participants (Emails missing)", expanded=False):
                    st.write("The following participants were detected but no email address was found in integrated sources:")
                    for info in unresolved_info:
                        st.markdown(f"- {info}")
                    st.caption("You can add their emails manually in the table below to include them in the dispatch.")

            # Use data editor for clean manual entry
            edited_recipients = st.data_editor(
                email_data,
                num_rows="dynamic",
                use_container_width=True,
                key=f"dispatch_recipients_{meeting_id or 'new'}",
                column_config={
                    "Source": st.column_config.TextColumn(disabled=True)
                }
            )
            # Send button
            if st.button("Finalize & Distribute Report", type="primary", use_container_width=True):
                # Extract valid emails
                verified_emails = [row.get("Email", "").strip() for row in edited_recipients if row.get("Email", "").strip()]
                
                if not verified_emails:
                    st.warning("Please specify at least one verified recipient. Enter an email in the 'Email' column above.")
                    print(f"DEBUG Dispatch: No verified emails found in editor. Content: {edited_recipients}")
                else:
                    print(f"DEBUG Dispatch: Initiating transmission to {len(verified_emails)} recipients...")
                    with st.spinner("Transmitting encrypted intelligence..."):
                        # Use EDITED content for the email
                        results = st.session_state.email_sender.send_meeting_summary(
                            recipient_emails=verified_emails,
                            summary=edited_summary,
                            action_items=action_items,
                            meeting_title=edited_title,
                            date=datetime.now().strftime("%Y-%m-%d"),
                            transcript_text=edited_transcript
                        )
                        print(f"DEBUG Dispatch: Transmission results: {results}")
                        
                        # Save mapping back to DB if meeting exists
                        if meeting_id and results["successes"]:
                            # Build structured mapping of successfully sent emails
                            new_recipients = []
                            for row in edited_recipients:
                                email = row.get("Email", "").strip()
                                if email in results["successes"]:
                                    new_recipients.append({
                                        "name": row.get("Display Name", "Unknown"),
                                        "email": email,
                                        "source": row.get("Source", "Manual Entry")
                                    })
                            
                            if new_recipients:
                                # Update DB with structured data
                                db.update_meeting_recipients(meeting_id, new_recipients)
                            
                            # Log history
                            db.add_email_event(meeting_id, {
                                "attempted": verified_emails,
                                "successes": results["successes"],
                                "failures": results["failures"],
                                "invalid": results["invalid_format"]
                            })

                        if results["successes"]:
                            st.success(f"Intelligence report successfully transmitted to {len(results['successes'])} recipients.")
                            if results["failures"]:
                                st.warning(f"Failed to deliver to: {', '.join(results['failures'])}")
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
        with st.spinner("Saving to database..."):
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
                },
                summary=summary,
                action_items=action_items
            )
        
        st.success("Meeting processed and saved successfully!")
        st.balloons()
        
        # Dispatch Center
        st.markdown("---")
        st.markdown("### Communication Dispatch")
        st.markdown("Verify details and distribute the meeting intelligence report.")
        
        dispatch_summary(summary, action_items, title, participants_list, transcript_text, meeting_id=meeting_id)
        
    except Exception as e:
        st.error(f"Error processing meeting: {e}")
        import traceback
        st.code(traceback.format_exc())

@st.dialog("Configure & Send Email")
def render_email_dispatch_modal(meeting):
    st.write(f"Configure email payload for: **{meeting.get('title', 'Unknown')}**")
    
    st.subheader("1. Recipients")
    
    # 1. Recipient Data Preparation
    email_data = []
    unresolved_info = []
    
    # Check new structured field first (Caching Layer)
    resolved_recipients = meeting.get('resolved_recipients', [])
    unresolved_participants = meeting.get('unresolved_participants', [])
    
    if resolved_recipients:
        print(f"DEBUG: Loading cached recipients from DB for archive meeting {meeting['meeting_id']}")
        email_data = [{"Display Name": r['name'], "Email": r['email'], "Source": f"{r['source']} (Cached)"} for r in resolved_recipients]
        for u in unresolved_participants:
            unresolved_info.append(f"{u['name']} ({u.get('source', 'Unknown')} - Cached)")
    else:
        # If no cache, try legacy emails or automatic resolution
        legacy_emails = meeting.get('resolved_emails', {})
        if legacy_emails:
            print(f"DEBUG: Loading legacy emails for archive meeting {meeting['meeting_id']}")
            email_data = [{"Display Name": name, "Email": email, "Source": "Legacy Stored"} for name, email in legacy_emails.items()]
        
        # If still no emails, try to resolve automatically
        if not email_data and meeting.get('meeting_url'):
            print(f"DEBUG: No cache found. Attempting resolution for archive meeting {meeting['meeting_id']}")
            with st.spinner("Attempting to resolve recipients..."):
                resolution = st.session_state.recipient_resolver.resolve_all(
                    meeting.get('meeting_url'),
                    participants=meeting.get('participants', []),
                    start_time=None
                )
                print(f"DEBUG: Resolution complete. Found {len(resolution['resolved'])} resolved.")
                
                for r in resolution['resolved']:
                    email_data.append({"Display Name": r['name'], "Email": r['email'], "Source": r['source']})
                for u in resolution['unresolved']:
                    unresolved_info.append(f"{u['name']} ({u['source']})")
                
                # Save results back to DB
                if resolution['resolved'] or resolution['unresolved']:
                    db.update_meeting_recipients(
                        meeting['meeting_id'], 
                        resolution['resolved'], 
                        resolution['unresolved']
                    )

    # Final fallback: manual entry rows for participants
    if not email_data:
        st.info("No participant emails were stored for this meeting. You can enter them manually below.")
        participants = meeting.get('participants', [])
        if isinstance(participants, list):
            email_data = [{"Display Name": p, "Email": "", "Source": "Manual Entry"} for p in participants]
        elif isinstance(participants, str):
            email_data = [{"Display Name": p.strip(), "Email": "", "Source": "Manual Entry"} for p in participants.split(",") if p.strip()]
        else:
            email_data = []
            
    if not email_data:
        email_data = [{"Display Name": "", "Email": "", "Source": "Manual Entry"}]

    # Display unresolved participants
    if unresolved_info:
        with st.expander("Unresolved Participants (Emails missing)", expanded=False):
            for info in unresolved_info:
                st.markdown(f"- {info}")

    edited_recipients = st.data_editor(
        email_data,
        num_rows="dynamic",
        use_container_width=True,
        key=f"recipients_{meeting['meeting_id']}",
        column_config={
            "Source": st.column_config.TextColumn(disabled=True)
        }
    )
    
    st.subheader("2. Draft Action Items")
    st.caption("Draft edits will apply to the email only and will NOT irreversibly overwrite the archive DB.")
    
    actions = db.get_action_items(meeting_id=meeting['meeting_id'])
    if actions:
        action_data = [{"Task": a.get("task", ""), "Assignee": a.get("assignee_name", a.get("owner", "")), "Deadline": a.get("deadline", "")} for a in actions]
    else:
        action_data = [{"Task": "", "Assignee": "", "Deadline": ""}]
        
    edited_actions = st.data_editor(
        action_data,
        num_rows="dynamic",
        use_container_width=True,
        key=f"actions_{meeting['meeting_id']}"
    )
    
    st.subheader("3. Content Toggles")
    c1, c2, c3 = st.columns(3)
    with c1:
        inc_sum = st.checkbox("Include Summary", value=True)
    with c2:
        inc_act = st.checkbox("Include Actions", value=True)
    with c3:
        inc_trn = st.checkbox("Include Transcript", value=False)
        
    if st.button("Dispatch Emails", type="primary", use_container_width=True):
        recipient_emails = [row.get("Email", "").strip() for row in edited_recipients if row.get("Email", "").strip()]
        
        draft_actions = [{"task": r.get("Task", ""), "assignee_name": r.get("Assignee", ""), "deadline": r.get("Deadline", "")} for r in edited_actions if str(r.get("Task", "")).strip()]
        
        with st.spinner("Dispatching via SMTP..."):
            results = st.session_state.email_sender.send_meeting_summary(
                recipient_emails=recipient_emails,
                summary=meeting.get('summary', ''),
                action_items=draft_actions,
                meeting_title=meeting.get('title', 'Unknown'),
                date=meeting.get('date', '')[:10],
                include_summary=inc_sum,
                include_actions=inc_act,
                include_transcript=inc_trn,
                transcript_text=meeting.get('transcript', '')
            )
            
            # Save mapping strictly for successfully validated and transmitted addresses
            if results["successes"]:
                valid_emailset = set(results["successes"])
                new_recipients = []
                for row in edited_recipients:
                    email = row.get("Email", "").strip()
                    if email in valid_emailset:
                        new_recipients.append({
                            "name": row.get("Display Name", "Unknown"),
                            "email": email,
                            "source": row.get("Source", "Manual Entry")
                        })
                
                if new_recipients:
                    # Update DB with structured data
                    db.update_meeting_recipients(meeting['meeting_id'], new_recipients)
            
            db.add_email_event(meeting['meeting_id'], {
                "attempted": recipient_emails,
                "successes": results["successes"],       # successfully attempted
                "failures": results["failures"],         # smtp level failure
                "invalid": results["invalid_format"]     # regex format failure
            })
            
            if results["successes"]:
                st.success(f"Sent successfully to: {', '.join(results['successes'])}")
            
            if results["invalid_format"]:
                st.warning(f"Invalid format (skipped): {', '.join(results['invalid_format'])}")
            if results["failures"]:
                st.error(f"Failed to deliver: {', '.join(results['failures'])}")

@st.dialog("Create Calendar Invite", width="large")
def render_reminder_creation_modal(meeting: dict, target_item_id: str = None):
    """
    Review modal for creating Google Calendar invites.
    If target_item_id is provided, only shows that specific task.
    """
    st.markdown(f"### Create Invite for: **{meeting.get('title', 'Meeting')}**")
    st.caption("This will create a reminder event on your calendar and invite the assignee as an attendee.")
    
    # Check if a Google account is connected
    accounts = db.get_connected_accounts()
    if not accounts:
        st.error("No Google accounts connected. Go to **Settings > Profile** to connect an account.")
        return
    
    # Let user pick which account to use if multiple
    if len(accounts) > 1:
        account_options = {acc['email']: acc for acc in accounts}
        selected_email = st.selectbox("Select Organizer Account", options=list(account_options.keys()))
        selected_account = account_options[selected_email]
    else:
        selected_account = accounts[0]
        st.info(f"Using Organizer Account: **{selected_account['email']}**")

    # Check for write scope
    granted_scopes = selected_account.get('granted_scopes', [])
    if 'https://www.googleapis.com/auth/calendar.events' not in granted_scopes:
        st.warning("Your account was connected with read-only permissions.")
        st.markdown("Please disconnect and reconnect in **Settings > Profile** to enable reminder creation.")
        return

    # Fetch action items
    actions = db.get_action_items(meeting_id=meeting['meeting_id'])
    if not actions:
        st.info("No action items found for this meeting.")
        return

    # Filter by target item if provided
    if target_item_id:
        actions = [a for a in actions if str(a['_id']) == str(target_item_id)]
        if not actions:
            st.error("Selected task not found.")
            return
        st.info("Showing specific task only.")
        if st.button("Show all tasks from this meeting", use_container_width=False):
            st.session_state.at_show_all_m = meeting['meeting_id']
            st.rerun()

    if st.session_state.get('at_show_all_m') == meeting['meeting_id']:
        # Reset and show all (this logic is simplified for the dialog scope)
        pass 

    st.divider()
    
    # Process and display items
    for idx, item in enumerate(actions):
        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Task:** {item['task']}")
                if item.get('evidence'):
                    st.caption(f"Context: \"{item['evidence']}\"")
            
            with col2:
                # 1. Resolve email
                resolved_email, source = resolve_assignee_email(item.get('assignee_name', ''), meeting)
                
                # 2. Parse deadline (Suggested Fallback logic)
                raw_deadline = item.get('deadline', '')
                parsed_date = parse_deadline(raw_deadline)
                is_suggested = False
                
                if not parsed_date:
                    # Default to 7 days from today if vague/missing
                    parsed_date = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=7)
                    is_suggested = True
                
                # Input for Email
                assignee_email = st.text_input(
                    "Assignee Email", 
                    value=resolved_email or "", 
                    key=f"email_input_{idx}_{meeting['meeting_id']}",
                    help=f"Source: {source or 'Unresolved'}"
                )
                
                # Input for Deadline
                label = "Deadline" + (" (Suggested: T+7d)" if is_suggested else "")
                deadline_val = st.date_input(
                    label, 
                    value=parsed_date.date(),
                    key=f"date_input_{idx}_{meeting['meeting_id']}"
                )
                
                # Status and Creation
                rem_status = item.get('reminder_status', 'not_created')
                
                if rem_status == 'created':
                    st.success("Invite sent")
                    if st.button("Re-send Invite", key=f"resend_{idx}_{meeting['meeting_id']}", use_container_width=True):
                        st.session_state[f"force_retry_{idx}_{meeting['meeting_id']}"] = True
                
                if rem_status != 'created' or st.session_state.get(f"force_retry_{idx}_{meeting['meeting_id']}"):
                    if not assignee_email:
                        st.warning("Email required to send invite")
                    
                    if st.button("Create Calendar Invite", key=f"create_{idx}_{meeting['meeting_id']}", disabled=not assignee_email, use_container_width=True, type="primary"):
                        # Combine date and time (default to 5 PM)
                        target_dt = datetime.combine(deadline_val, datetime.min.time()).replace(hour=17)
                        
                        # Add disclaimer if suggested
                        item_copy = item.copy()
                        if is_suggested:
                            item_copy['evidence'] = (item.get('evidence', '') + 
                                "\n\n[NOTE] No explicit deadline was detected in the meeting transcript. "
                                "This reminder date was defaulted to 7 days after the meeting by the organizer. "
                                "If this is incorrect, please contact the assigner.")
                        
                        with st.spinner("Creating invite..."):
                            result = create_reminder_event(
                                account_email=selected_account['email'],
                                action_item=item_copy,
                                deadline=target_dt,
                                attendee_email=assignee_email,
                                meeting_title=meeting.get('title', 'Meeting'),
                                meeting_date=meeting.get('date', '')[:10],
                                meeting_id=meeting['meeting_id']
                            )
                            
                            if result['success']:
                                st.success("Invite sent!")
                                # Update DB
                                update_data = {
                                    'reminder_status': 'created',
                                    'calendar_event_id': result['event_id'],
                                    'reminder_created_at': datetime.now(),
                                    'reminder_created_by_account': selected_account['email'],
                                    'resolved_assignee_email': assignee_email
                                }
                                db.action_items.update_one({'_id': item['_id']}, {'$set': update_data})
                                if f"force_retry_{idx}_{meeting['meeting_id']}" in st.session_state:
                                    del st.session_state[f"force_retry_{idx}_{meeting['meeting_id']}"]
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"Error: {result['error']}")

def past_meetings_page():
    """View past meetings and ask questions"""
    st.header("Meeting Archive")
    
    try:
        meetings = db.get_all_meetings(limit=50)
        
        if not meetings:
            st.info("No meetings processed yet. Start a new session or upload a recording.")
            return
        
        # Search and filter
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("Search", placeholder="Search by title, participants...", label_visibility="collapsed")
        with col2:
            filter_type = st.selectbox("Category", ["All", "Live Sessions", "Recordings"], label_visibility="collapsed")
        
        # Apply filters
        # Reverse chronological mapping
        filtered_meetings = sorted(meetings, key=lambda x: x.get('date', ''), reverse=True)
        
        if search_query:
            filtered_meetings = [m for m in filtered_meetings if 
                       search_query.lower() in m.get('title', '').lower() or
                       search_query.lower() in str(m.get('participants', [])).lower()]
        
        if filter_type == "Live Sessions":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'live_meeting']
        elif filter_type == "Recordings":
            filtered_meetings = [m for m in filtered_meetings if m.get('meeting_type') == 'uploaded_recording']
            
        st.caption(f"{len(filtered_meetings)} sessions found")
        
        # Display meetings
        for meeting in filtered_meetings:
            meeting_type = meeting.get('meeting_type', 'uploaded_recording')
            type_label = "LIVE" if meeting_type == 'live_meeting' else "REC"
            title = meeting.get('title', 'Untitled')
            date_str = meeting.get('date', 'Unknown')[:10]
            
            # Extract a very short summary preview for the header
            raw_sum = meeting.get('summary', '')
            sum_preview = raw_sum[:70].replace('\n', ' ') + "..." if len(raw_sum) > 70 else raw_sum.replace('\n', ' ')
            if not sum_preview.strip():
                sum_preview = "No summary generated."
                
            # Compose card title string
            title_text = f"{type_label} {title}  |  {date_str}  |  {sum_preview}"
            
            with st.expander(title_text, expanded=False):
                
                # Meta info row
                st.markdown(f"**Meeting:** {title} &nbsp;|&nbsp; **Date:** {meeting.get('date', 'Unknown')[:19]} &nbsp;|&nbsp; **Duration:** {meeting.get('duration', 0):.1f}s")
                st.markdown(f"**Participants:** {', '.join(meeting.get('participants', ['Not specified']))}")
                
                _, btn_col, rem_col, del_col = st.columns([3, 1, 1, 1])
                with btn_col:
                    if st.button("Send Summary", key=f"email_{meeting['meeting_id']}", use_container_width=True):
                        render_email_dispatch_modal(meeting)
                with rem_col:
                    if st.button("Reminders", key=f"remind_{meeting['meeting_id']}", use_container_width=True):
                        render_reminder_creation_modal(meeting)
                with del_col:
                    if st.button("Delete", key=f"del_{meeting['meeting_id']}", use_container_width=True):
                        with st.spinner("Removing..."):
                            db.delete_meeting(meeting['meeting_id'])
                            st.session_state.vector_store.delete_meeting(meeting['meeting_id'])
                            st.rerun()
                
                st.divider()
                
                # --- SECTION 1: CLEANED TRANSCRIPT ---
                st.subheader("Cleaned Transcript")
                clean_t = meeting.get('transcript', 'No cleaned transcript available.')
                
                with st.container(height=350, border=True):
                    # Default formatting instead of HTML chat bubbles
                    for paragraph in clean_t.split('\n\n'):
                        if paragraph.strip():
                            st.markdown(paragraph.strip())
                
                # --- SECTION 2: SUMMARY ---
                st.subheader("Analytical Summary")
                with st.container(border=True):
                    st.markdown(meeting.get('summary', 'No summary generated.'))
                
                # --- SECTION 3: ACTION ITEMS ---
                st.subheader("Action Items")
                actions = db.get_action_items(meeting_id=meeting['meeting_id'])
                
                if actions:
                    for idx, item in enumerate(actions, 1):
                        task = item.get('task', 'Unknown task')
                        assignee = item.get('assignee_name', 'Unassigned')
                        deadline = item.get('deadline', 'N/A')
                        confidence = str(item.get('confidence', 'medium')).capitalize()
                        evidence = item.get('evidence', '')
                        
                        # Use simple, clean default Streamlit markdown layout instead of custom HTML
                        st.markdown(f"**{idx}. {task}**")
                        st.caption(f"**Assignee:** {assignee} | **Deadline:** {deadline} | **Confidence:** {confidence}")
                        if evidence:
                            st.info(f"Evidence: \"{evidence}\"")
                        st.write("") # small spacing
                else:
                    st.info("No direct action items identified.")
                
                # --- SECTION 4: RAW TRANSCRIPT ---
                with st.expander("View Raw Transcript (Debug)"):
                    raw_text = meeting.get('raw_transcript', meeting.get('transcript', 'Unavailable.'))
                    st.text_area("JSON / Whisper Fallback", raw_text, height=200, key=f"raw_{meeting['meeting_id']}", label_visibility="collapsed")
                    
                st.divider()
                
                # --- ASK INTELLIGENCE ---
                with st.container(border=True):
                    st.markdown("**Session Intelligence**")
                    question = st.text_input(
                        "Inquire about this specific meeting:", 
                        placeholder="e.g. 'What was the final decision on the architectural redesign?'",
                        key=f"q_{meeting['meeting_id']}"
                    )
                    
                    if question:
                        with st.spinner("Analyzing context..."):
                            try:
                                meeting_context = f"Meeting Title: {title}\nDate: {date_str}\n\nTRANSCRIPT:\n{meeting.get('transcript', '')}"
                                answer = st.session_state.summary_agent.answer_question(
                                    transcript=meeting_context,
                                    question=question
                                )
                                st.markdown("**AI Assistant:**")
                                st.success(answer)
                            except Exception as e:
                                st.error(f"Error communicating with LLM: {e}")
        
    except Exception as e:
        st.error(f"Failed to load archive: {e}")

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
                    sources = st.session_state.context_agent.search_meetings(query, n_results=5)
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
    
    # Closest Deadline Warning Banner
    try:
        deadline_warning = get_closest_deadline_warning(db)
        if deadline_warning:
            urgency = deadline_warning['urgency']
            label = deadline_warning['label']
            task = deadline_warning['task']
            assignee = deadline_warning['assignee']
            deadline_date = deadline_warning['deadline_date']
            
            banner_text = f"**Closest Deadline: {label}**  \n"
            banner_text += f"**Task:** {task}  \n"
            banner_text += f"**Assignee:** {assignee}  \n"
            banner_text += f"**Deadline:** {deadline_date.strftime('%B %d, %Y')}"
            
            if urgency == 'overdue':
                st.error(banner_text)
            elif urgency in ('due_today', 'due_tomorrow'):
                st.warning(banner_text)
            else:
                st.info(banner_text)
            
            st.divider()
    except Exception as e:
        # Silently skip — deadline warning is non-critical
        print(f"[WARNING] Action Tracker deadline banner error: {e}")
    
    try:
        # 1. Get all action items
        all_items = db.get_action_items()
        if not all_items:
            st.info("No action items found")
            return

        # 2. Group by Meeting
        from collections import defaultdict
        meeting_groups = defaultdict(list)
        for item in all_items:
            m_id = item.get('meeting_id', 'unlinked')
            meeting_groups[m_id].append(item)
        
        # 3. Get meeting metadata for headers
        meeting_metadata = {}
        for m_id in meeting_groups.keys():
            if m_id != 'unlinked':
                m_obj = db.get_meeting(m_id)
                if m_obj:
                    meeting_metadata[m_id] = m_obj
        
        # Sort meeting IDs by date (newest first)
        sorted_m_ids = sorted(
            meeting_groups.keys(), 
            key=lambda mid: meeting_metadata.get(mid, {}).get('date', '1970-01-01'), 
            reverse=True
        )

        # 4. Filter logic (Owner only)
        owner_filter = st.text_input("Filter by Owner/Assignee", placeholder="Type a name to filter...")
        if owner_filter:
            for m_id in sorted_m_ids:
                meeting_groups[m_id] = [item for item in meeting_groups[m_id] if 
                                       (owner_filter.lower() in str(item.get('owner', '') or '').lower()) or
                                       (owner_filter.lower() in str(item.get('assignee_name', '') or '').lower())]
            # Remove empty groups
            sorted_m_ids = [mid for mid in sorted_m_ids if meeting_groups[mid]]

        # 5. Pagination (5 meetings per page) - Arrow Wise Style
        MEETINGS_PER_PAGE = 5
        total_pages = (len(sorted_m_ids) + MEETINGS_PER_PAGE - 1) // MEETINGS_PER_PAGE
        
        if "at_page" not in st.session_state:
            st.session_state.at_page = 1
            
        if total_pages > 1:
            pcol1, pcol2, pcol3, pcol4 = st.columns([1, 1, 1, 10])
            with pcol1:
                if st.button("<", disabled=(st.session_state.at_page <= 1)):
                    st.session_state.at_page -= 1
                    st.rerun()
            with pcol2:
                st.markdown(f"### {st.session_state.at_page}")
            with pcol3:
                if st.button(">", disabled=(st.session_state.at_page >= total_pages)):
                    st.session_state.at_page += 1
                    st.rerun()
            st.caption(f"Showing page {st.session_state.at_page} of {total_pages} ({len(sorted_m_ids)} meetings)")
        else:
            st.session_state.at_page = 1
            
        start_idx = (st.session_state.at_page - 1) * MEETINGS_PER_PAGE
        end_idx = start_idx + MEETINGS_PER_PAGE
        page_m_ids = sorted_m_ids[start_idx:end_idx]

        # 6. Display Groups
        for m_id in page_m_ids:
            items = meeting_groups[m_id]
            m_meta = meeting_metadata.get(m_id, {})
            
            title = m_meta.get('title', 'Unlinked Actions') if m_id != 'unlinked' else "Unlinked Actions"
            date = m_meta.get('date', '')[:10] if m_id != 'unlinked' else ""
            
            st.markdown(f"### {title}  `{date}`")
            
            # Limiting: Show max 10 tasks initially
            LIMIT = 10
            show_all = st.checkbox(f"Show all {len(items)} tasks", key=f"show_all_{m_id}") if len(items) > LIMIT else True
            display_items = items if show_all else items[:LIMIT]
            
            for item in display_items:
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([2.5, 1, 1, 1, 1])
                    
                    # Status Lifecycle logic
                    status = item.get('status', 'pending')
                    rem_status = item.get('reminder_status', 'not_created')
                    
                    # Compute deadline urgency
                    deadline_str = item.get('deadline', 'N/A')
                    parsed_deadline = parse_deadline(deadline_str)
                    
                    with c1:
                        priority_label = {"high": "HIGH", "medium": "MED", "low": "LOW"}
                        label = priority_label.get(item.get('priority', 'medium'), 'MED')
                        st.markdown(f"**{label} - {item['task']}**")
                        
                        # Re-add Calendar button per task
                        m_id_link = item.get('meeting_id')
                        if m_id_link and m_id_link != 'unlinked':
                            if st.button("Create Invite", key=f"rem_track_{item['_id']}", use_container_width=False, type="secondary", help="Create calendar invite for this item"):
                                m_obj = db.get_meeting(m_id_link)
                                if m_obj:
                                    render_reminder_creation_modal(m_obj, target_item_id=item['_id'])
                    
                    with c2:
                        assignee = item.get('owner') or item.get('assignee_name') or 'Unassigned'
                        st.caption(f"Assignee: {assignee}")
                    
                    with c3:
                        st.caption(f"Deadline: {item.get('deadline', 'N/A')}")
                    
                    with c4:
                        # Derive Status Label
                        if status == 'completed':
                            st.success("Completed")
                        elif rem_status == 'created':
                            st.info("Invite Sent")
                        elif parsed_deadline:
                            now = datetime.now()
                            if parsed_deadline < now:
                                st.error("Overdue")
                            elif parsed_deadline.date() == now.date():
                                st.warning("Due Today")
                            else:
                                st.success("Upcoming")
                        else:
                            st.caption("Pending")
                    
                    with c5:
                        # Minimal completion toggle
                        if status != 'completed':
                            if st.button("Mark Done", key=f"done_{item['_id']}", use_container_width=True):
                                db.update_action_item_status(item['_id'], 'completed')
                                st.rerun()
                        else:
                            if st.button("Undo", key=f"undo_{item['_id']}", use_container_width=True):
                                db.update_action_item_status(item['_id'], 'pending')
                                st.rerun()

            if not show_all:
                st.caption(f"+ {len(items) - LIMIT} more tasks in this meeting.")
            
            st.divider()

    except Exception as e:
        st.error(f"Error loading action items: {e}")
        import traceback
        st.code(traceback.format_exc())
        
    except Exception as e:
        st.error(f"Error loading action items: {e}")

if __name__ == "__main__":
    main()
