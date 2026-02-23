# 🚀 Complete Setup Guide

Step-by-step instructions to get your AI Meeting Assistant running.

## ⏱️ Estimated Time: 15-20 minutes

---

## Step 1: System Requirements

### Check Python Version
```bash
python --version  # Should be 3.8 or higher
```

If not installed, download from [python.org](https://www.python.org/downloads/)

### Install FFmpeg

**macOS (using Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
1. Download from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to System PATH

**Verify installation:**
```bash
ffmpeg -version
```

---

## Step 2: Get API Keys

### 2.1 Groq API Key (Required - FREE)

1. Go to [console.groq.com](https://console.groq.com)
2. Click "Sign Up" (free account)
3. After login, click "API Keys" in sidebar
4. Click "Create API Key"
5. Name it "Meeting Assistant"
6. Copy the key (starts with `gsk_...`)

**Important:** Save this key! You won't see it again.

### 2.2 MongoDB Atlas (Required - FREE)

1. Go to [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Sign up for free account
3. Create a new project (e.g., "MeetingAssistant")
4. Build a Database → Choose **FREE M0** cluster
5. Select your closest region
6. Wait 3-5 minutes for cluster creation

**Get Connection String:**
1. Click "Connect" on your cluster
2. Choose "Connect your application"
3. Copy the connection string
4. Replace `<password>` with your actual password
5. Replace `<dbname>` with `meeting_assistant`

Example:
```
mongodb+srv://myuser:mypassword@cluster0.abcde.mongodb.net/meeting_assistant
```

**Setup Database Access:**
1. Click "Database Access" in left sidebar
2. Click "Add New Database User"
3. Create username and password (save these!)
4. Set "Database User Privileges" to "Read and write to any database"

**Setup Network Access:**
1. Click "Network Access" in left sidebar
2. Click "Add IP Address"
3. Click "Allow Access from Anywhere" (for testing)
4. Click "Confirm"

---

## Step 3: Project Setup

### 3.1 Clone or Download Project

```bash
# If using git
git clone <repository-url>
cd ai-meeting-assistant

# Or download and extract ZIP
cd ai-meeting-assistant
```

### 3.2 Create Virtual Environment

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### 3.3 Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will take 5-10 minutes. Go grab coffee! ☕

**If you get errors:**
- Make sure you're in the virtual environment
- Try: `pip install --upgrade pip setuptools wheel`
- Then retry: `pip install -r requirements.txt`

---

## Step 4: Configuration

### 4.1 Create .env File

```bash
# Copy example file
cp .env.example .env

# Or on Windows
copy .env.example .env
```

### 4.2 Edit .env File

Open `.env` in any text editor and fill in:

```env
# Your Groq API Key
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx

# Your MongoDB Connection String
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/
MONGODB_DB_NAME=meeting_assistant

# Whisper Model (start with base)
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
```

**Save the file!**

---

## Step 5: Create Required Directories

The app will create these automatically, but you can create them manually:

```bash
mkdir -p data/meetings data/transcripts data/chromadb
```

Or on Windows:
```bash
mkdir data\meetings data\transcripts data\chromadb
```

---

## Step 6: Test Installation

### 6.1 Test Environment

```bash
python -c "import whisper; import groq; import chromadb; print('✅ All packages installed!')"
```

Should see: `✅ All packages installed!`

### 6.2 Test Configuration

```bash
python -c "from config import settings; print('✅ Configuration loaded!')"
```

Should see: `✅ Configuration loaded!`

If you see errors about missing API keys, double-check your `.env` file.

---

## Step 7: Run the Application

### Start the App

```bash
streamlit run ui/streamlit_app.py
```

Or:
```bash
python main.py
```

**First Launch:**
- Takes 1-2 minutes to download Whisper model (one-time)
- Downloads sentence-transformers model (one-time)
- Browser should open automatically to `http://localhost:8501`

**If browser doesn't open:**
- Manually go to: `http://localhost:8501`

---

## Step 8: Meeting Bot Setup (Optional)

The Meeting Bot automatically joins live meetings (Zoom/Google Meet), captures audio in real-time, and transcribes/analyzes on-the-fly.

### 8.1 Install Playwright

```bash
pip install playwright==1.41.0
playwright install chromium
```

This downloads the Chromium browser (takes 2-3 minutes, ~300MB).

### 8.2 Enable Virtual Audio Device

**Windows - Enable Stereo Mix (Built-in):**

1. Right-click the speaker icon in taskbar → "Sounds"
2. Go to "Recording" tab
3. Right-click empty space → Check "Show Disabled Devices"
4. You should see "Stereo Mix"
5. Right-click "Stereo Mix" → "Enable"
6. Right-click "Stereo Mix" → "Set as Default Device"
7. Click "OK"

**If you don't see Stereo Mix:**
- Update audio drivers from manufacturer website
- Or install VB-CABLE (Virtual Audio Device):
  1. Download from [vb-audio.com/Cable](https://vb-audio.com/Cable/)
  2. Extract and run setup as Administrator
  3. Restart computer
  4. Set "CABLE Output" as default recording device

### 8.3 Test Audio Device

```bash
python integrations/audio_device_helper.py
```

This will:
- List all audio devices
- Help you find the correct device
- Test audio capture
- Save device ID for later use

**Expected output:**
```
Available Audio Devices:
Device 0: Microphone (Realtek Audio)
Device 1: Stereo Mix (Realtek Audio) ✓ [RECOMMENDED]
Device 2: Line In

Testing device 1 (Stereo Mix)...
✅ Audio capture successful!
```

### 8.4 Test Meeting Bot

1. Start the Streamlit app:
```bash
streamlit run ui/streamlit_app.py
```

2. Navigate to "🤖 Join Live Meeting"
3. Select your audio device (e.g., "Stereo Mix")
4. Enter a test meeting URL:
   - **Google Meet:** Create instant meeting at [meet.google.com/new](https://meet.google.com/new)
   - **Zoom:** Get meeting link from Zoom app
5. Click "Join Meeting"

**What happens:**
- Browser opens automatically
- Bot joins meeting as guest
- Audio capture starts
- Real-time transcription begins
- Results appear in the app

**First run notes:**
- Google Meet may ask you to sign in (60 seconds to complete)
- Bot will join with camera/mic off
- You'll see transcription appear every 30 seconds

### 8.5 Troubleshooting Meeting Bot

**"Invalid device" error:**
- Stereo Mix is disabled → Enable it (see Step 8.2)
- Or select a different device from dropdown

**Browser closes immediately:**
- Audio device not working → Test with Step 8.3
- Try selecting "Microphone" for testing

**"Timeout exceeded" error:**
- Slow internet connection
- Google Meet took too long to load
- Bot will retry automatically

**No audio captured:**
- Play system audio (music/YouTube) while testing
- Check Windows Sound settings → Stereo Mix is default
- Check audio levels in Sound Control Panel

**Google Meet won't let bot join:**
- Meeting may require login
- Bot pauses 60 seconds for you to sign in
- Or create an instant meeting (no login needed)

**Zoom "Join from Browser" not working:**
- Enable in Zoom settings:
  1. Go to [zoom.us/profile/setting](https://zoom.us/profile/setting)
  2. Enable "Join from Browser"

---

## Step 9: Test with Sample Meeting

### 9.1 Get Test Audio

Option 1: Record yourself
- Record a 1-2 minute audio on your phone
- Say: "This is a test meeting. John will review the budget by Friday. Sarah will send the report."
- Transfer to your computer

Option 2: Use online TTS
- Go to [ttsmaker.com](https://ttsmaker.com)
- Paste sample text
- Download as MP3

### 9.2 Process Meeting

1. In the app, click "🎙️ New Meeting"
2. Enter title: "Test Meeting"
3. Enter participants: "John, Sarah"
4. Upload your audio file
5. Click "🚀 Process Meeting"
6. Wait for results (1-3 minutes for first run)

**You should see:**
- ✅ Transcription
- ✅ Summary
- ✅ Action items

---

## Step 10: Verify Everything Works

### Check Database
1. Go to MongoDB Atlas dashboard
2. Click "Browse Collections"
3. You should see:
   - `meetings` collection with 1 document
   - `action_items` collection

### Check Vector Store
```bash
ls data/chromadb/
```
Should see several files (ChromaDB storage)

### Test RAG
1. In app, click "💬 Ask Questions"
2. Type: "What did we discuss?"
3. Should get relevant answer

---

## 🎉 Success! You're Ready!

### What to Do Next

1. **Process real meetings**: Upload actual meeting audio
2. **Explore features**: Try all 4 pages in the sidebar
3. **Customize**: Edit `config/settings.py` for your needs
4. **Extend**: Add custom agents or integrations

---

## 🐛 Troubleshooting Common Issues

### "Module not found" error
```bash
# Reinstall specific package
pip install <package-name>
```

### "GROQ_API_KEY not found"
- Check `.env` file exists in project root
- Check no spaces around `=` sign
- Check file is named `.env` not `.env.txt`

### "MongoDB connection error"
- Verify connection string is correct
- Check Network Access allows your IP
- Check database user has correct permissions

### Whisper model download fails
```bash
# Download manually
python -c "import whisper; whisper.load_model('base')"
```

### Streamlit won't start
```bash
# Check if port is in use
lsof -i :8501  # macOS/Linux
netstat -ano | findstr :8501  # Windows

# Use different port
streamlit run ui/streamlit_app.py --server.port 8502
```

### Out of memory during transcription
- Use smaller Whisper model: `WHISPER_MODEL=tiny`
- Process shorter audio files
- Close other applications

### Meeting Bot: Stereo Mix not available
- Update audio drivers from device manufacturer
- Install VB-CABLE: [vb-audio.com/Cable](https://vb-audio.com/Cable/)
- Alternative: Use "Microphone" for testing (captures room audio)

### Meeting Bot: No transcription appearing
- Verify audio device is capturing sound (test with audio_device_helper.py)
- Play system audio (YouTube/music) while bot is in meeting
- Check Stereo Mix is enabled and set as default
- Try increasing system volume

---

## 📚 Additional Resources

- [Groq Documentation](https://console.groq.com/docs)
- [MongoDB Atlas Tutorial](https://docs.atlas.mongodb.com/getting-started/)
- [Whisper GitHub](https://github.com/openai/whisper)
- [Streamlit Documentation](https://docs.streamlit.io)

---

## 💡 Tips for Best Results

1. **Audio Quality**: Use clear audio with minimal background noise
2. **File Size**: Keep meetings under 60 minutes for best performance
3. **Participants**: Mention names in the audio for better action item extraction
4. **Questions**: Ask specific questions for better RAG results
5. **Regular Use**: The more meetings you process, the better RAG becomes
6. **Live Meetings**: Use Stereo Mix for Meeting Bot to capture system audio without room noise
7. **Meeting Bot**: Join meetings 1-2 minutes before start for smooth connection
8. **Audio Testing**: Always test audio device before important meetings

---

## 🆘 Still Having Issues?

1. Check all steps again carefully
2. Read error messages completely
3. Search the error on Google/StackOverflow
4. Create an issue on GitHub with:
   - Error message
   - Steps you took
   - Your OS and Python version

---

**Good luck building! 🚀**
