# 🎙️ AI Meeting Assistant - Technical Guide

Advanced Multi-Agent RAG System for Automated Meeting Intelligence.

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

## 📋 Prerequisites

- **Python**: 3.12+
- **Database**: MongoDB Atlas (Free M0)
- **LLM**: Groq API Key (Llama 3.3 70B)
- **Audio**: FFmpeg installed and in System PATH
- **Browser**: Playwright Chromium (`playwright install chromium`)
- **Audio Capture**: Virtual Loopback (Stereo Mix or VB-Audio Cable)

---

## 🏗️ System Architecture

- **Speech-to-Text**: OpenAI Whisper (Base)
- **LLM Engine**: Groq Cloud (Llama 3.3 70B)
- **Vector Store**: ChromaDB (all-MiniLM-L6-v2 embeddings)
- **Metadata DB**: MongoDB Atlas
- **UI Framework**: Streamlit 1.57.0

---

## 🚀 Installation

### 1. Python & Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# OR
.\.venv\Scripts\Activate.ps1 # Windows
pip install -r requirements.txt
playwright install chromium
```

### 2. FFmpeg Setup
- **Windows**: `winget install --id Gyan.FFmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

---

## 📁 Project Structure

```
ai-meeting-assistant/
├── agents/             # Summary & Action Item agents (Groq)
├── audio_processing/   # Whisper STT integration
├── config/             # Settings & Environment management
├── database/           # MongoDB Atlas client
├── integrations/       # Meeting Bot (Playwright) & Email
├── rag/                # ChromaDB vector store
├── ui/                 # Streamlit interface
└── data/               # Local storage for audio & vectors
```

---

## 🎯 Core Features

- **Live Meeting Bot**: Joins Zoom/Meet via Playwright, captures system audio.
- **Automated Transcription**: Whisper-based local/cloud transcription.
- **Multi-Agent Analysis**: Summary generation and Action Item extraction.
- **RAG Q&A**: Semantic search across meeting transcripts using ChromaDB.
- **Meeting Archive**: Persistent storage of transcripts and metadata in MongoDB.

---

## 🔧 Environment Configuration (.env)

```env
GROQ_API_KEY=gsk_...
MONGODB_URI=mongodb+srv://...
BOT_NAME=MeetAI
WHISPER_MODEL=base
```

---

## 🛠️ Usage

1. **New Meeting**: Upload audio files for offline processing.
2. **Live Session**: Enter a meeting URL to start the automated bot.
3. **Archive**: Browse past meetings and ask questions via the RAG interface.
4. **Action Tracker**: Monitor and update status of extracted tasks.
