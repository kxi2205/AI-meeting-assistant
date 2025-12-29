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
import config.settings as settings

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
                st.metric("Total Meetings", stats['total_meetings'])
                st.metric("Total Action Items", stats['total_action_items'])
                st.metric("Pending Actions", stats['pending_actions'])
            except Exception as e:
                st.error(f"Could not load stats: {e}")
        
        st.divider()
        
        # Navigation
        page = st.radio(
            "Navigate",
            ["🎙️ New Meeting", "📚 Past Meetings", "✅ Action Items"],
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
    elif page == "📚 Past Meetings":
        past_meetings_page()
    elif page == "✅ Action Items":
        action_items_page()

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
                "audio_file": str(audio_path)
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
        meetings = db.get_all_meetings(limit=20)
        
        if not meetings:
            st.info("No meetings found. Upload your first meeting!")
            return
        
        # Search
        search_query = st.text_input("🔍 Search meetings", placeholder="Search by title, participants...")
        
        # Filter meetings
        if search_query:
            meetings = [m for m in meetings if 
                       search_query.lower() in m.get('title', '').lower() or
                       search_query.lower() in str(m.get('participants', [])).lower()]
        
        st.write(f"Found {len(meetings)} meeting(s)")
        
        # Display meetings
        for meeting in meetings:
            with st.expander(f"🎙️ {meeting.get('title', 'Untitled')} - {meeting.get('date', '')[:10]}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"**Participants:** {', '.join(meeting.get('participants', []))}")
                    st.markdown(f"**Duration:** {meeting.get('duration', 0):.1f} seconds")
                    
                    # View Full Details button
                    if st.button("View Full Details", key=f"view_{meeting['meeting_id']}"):
                        st.markdown("### Summary")
                        st.markdown(meeting.get('summary', 'No summary available'))
                        
                        st.markdown("### Transcript")
                        st.text_area("", meeting.get('transcript', ''), height=200, 
                                   key=f"transcript_{meeting['meeting_id']}")
                    
                    # Ask Questions button
                    if st.button("💬 Ask Questions", key=f"ask_{meeting['meeting_id']}"):
                        st.session_state[f"show_qa_{meeting['meeting_id']}"] = True
                    
                    # Show Q&A interface if button was clicked
                    if st.session_state.get(f"show_qa_{meeting['meeting_id']}", False):
                        st.markdown("---")
                        st.markdown("### 💬 Ask Questions About This Meeting")
                        st.caption("Ask about this specific meeting or general questions for definitions, examples, ideas, etc.")
                        
                        question = st.text_input(
                            "Your question", 
                            placeholder="What was discussed? Or: What is steganography?",
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
                
                with col2:
                    # Action items count
                    actions = db.get_action_items(meeting_id=meeting['meeting_id'])
                    st.metric("Action Items", len(actions))
                    
                    if st.button("🗑️ Delete", key=f"del_{meeting['meeting_id']}"):
                        db.delete_meeting(meeting['meeting_id'])
                        st.session_state.vector_store.delete_meeting(meeting['meeting_id'])
                        st.rerun()
        
    except Exception as e:
        st.error(f"Error loading meetings: {e}")

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
