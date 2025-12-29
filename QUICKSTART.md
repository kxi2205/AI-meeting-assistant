# ⚡ Quick Start (5 Minutes)

Get up and running in 5 minutes!

## Prerequisites
- Python 3.8+
- FFmpeg installed
- Groq API key
- MongoDB connection string

Don't have these? See [SETUP_GUIDE.md](SETUP_GUIDE.md)

---

## 1. Install (2 minutes)

```bash
# Clone and enter directory
cd ai-meeting-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

---

## 2. Configure (1 minute)

Create `.env` file:

```env
GROQ_API_KEY=your_groq_key_here
MONGODB_URI=your_mongodb_uri_here
MONGODB_DB_NAME=meeting_assistant
WHISPER_MODEL=base
```

---

## 3. Run (30 seconds)

```bash
streamlit run ui/streamlit_app.py
```

---

## 4. Test (2 minutes)

1. Upload audio file
2. Enter meeting title
3. Click "Process Meeting"
4. Get transcript, summary, and action items!

---

## That's It! 🎉

**Next Steps:**
- Read [README.md](README.md) for full documentation
- See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed setup
- Check `examples/` for sample meetings

**Having issues?** See Troubleshooting in SETUP_GUIDE.md
