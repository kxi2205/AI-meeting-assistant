# 🎙️ AI Meeting Assistant - Technical Guide

Advanced Multi-Agent RAG System for Automated Meeting Intelligence.

---

## 👥 Quick Start for Teammates

1. **Environment Setup**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   playwright install chromium
   ```
2. **Configuration**:
   Copy `.env.example` to `.env` and fill in `GROQ_API_KEY` and `MONGODB_URI`.
3. **Run**:
   ```powershell
   streamlit run ui/streamlit_app.py
   ```

---

## 🏗️ System Architecture

The AI Meeting Assistant is built on a modular, multi-agent architecture:

- **Speech-to-Text**: Local OpenAI Whisper (Base) for high-accuracy transcriptions.
- **LLM Engine**: Groq Cloud (Llama 3.3 70B) for near-instant summary and action item extraction.
- **Vector Store**: ChromaDB with `all-MiniLM-L6-v2` embeddings for semantic RAG search.
- **Metadata Storage**: MongoDB Atlas for persistent meeting archives and task tracking.
- **Automation**: Playwright-based bot for joining and recording browser-based meetings.
- **UI Framework**: Streamlit for a fast, responsive intelligence dashboard.

---

## 🔇 Troubleshooting: Audio Loopback Issues

If you see the error **"Loopback device not found"** or the transcription is empty, follow this guide to set up your system correctly.

### 1. Enabling "Stereo Mix" (Easiest)
Windows has a built-in loopback device, but it is often disabled by default.
1. Right-click the **Sound Icon** in the taskbar > **Sound Settings**.
2. Scroll down to **More sound settings** (on Windows 11) or **Recording** tab.
3. Right-click in the list and check **"Show Disabled Devices"**.
4. If **Stereo Mix** appears, right-click it and select **Enable**.
5. **CRITICAL**: Right-click Stereo Mix > **Set as Default Device**.

### 2. Using VB-Audio Cable (Recommended)
If Stereo Mix isn't available or is noisy, use a virtual cable:
1. Download and install [VB-CABLE Virtual Audio Cable](https://vb-audio.com/Cable/).
2. Restart your computer after installation.
3. Set **CABLE Input** as your **Playback Default**.
4. Set **CABLE Output** as your **Recording Default**.

### 3. Verification inside the App
Once enabled/installed, use the **manual selector** in the app:
1. Go to the **Join Session** tab in the sidebar.
2. Open the **"🎤 Audio Configuration"** expander.
3. Click **"Refresh Devices"**.
4. Select **"Stereo Mix"** or **"CABLE Output"** from the dropdown.
5. If you see a green "✅ Audio loopback device ready" message, you are good to go!

---

## 📁 Project Structure

```
ai-meeting-assistant/
├── agents/             # Summary & Action Item agents (Groq)
├── audio_processing/   # Whisper STT integration
├── config/             # Settings & Environment management
├── database/           # MongoDB Atlas client
├── integrations/       # Meeting Bot (Playwright), Calendar & Email
├── rag/                # ChromaDB vector store
├── ui/                 # Streamlit interface
├── utils/              # Deadline parsing & Assignee resolution
└── data/               # Local storage for audio & vectors
```

---

## 🚀 Full Installation Details

### 1. FFmpeg Setup (Required for Whisper)
- **Windows**: `winget install --id Gyan.FFmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### 2. Python Dependencies
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

---

## 🎯 Features & Usage

1. **Live Meeting Bot**: Enters a URL (Zoom/Meet), joins the session, and captures loopback audio.
2. **Analytical Summary**: Generates high-level summaries and detailed action items using Llama 3.3.
3. **Calendar Reminders**: Create Google Calendar invites directly from extracted action items.
4. **Action Tracker**: Grouped, paginated view of all tasks with automated status lifecycles.
5. **Global Intelligence**: Ask questions about your entire meeting history using RAG.
