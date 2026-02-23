# Quick Fix Guide - Meeting Bot Audio Setup

## The Issues Fixed

1. **AsyncIO Error** - Fixed by running meeting bot in separate thread
2. **Audio Device Error** - Added device selection in UI and proper configuration

## How to Enable Stereo Mix (Windows)

**Step-by-step:**

1. Right-click the **speaker icon** 🔊 in your Windows taskbar (bottom-right)
2. Click **"Sounds"** or **"Open Sound settings"**
3. In the Sound Control Panel, go to the **"Recording"** tab
4. Right-click in the empty space and select:
   - ☑️ **"Show Disabled Devices"**
   - ☑️ **"Show Disconnected Devices"**
5. You should now see **"Stereo Mix"**
6. Right-click on **"Stereo Mix"** → Click **"Enable"**
7. Right-click on **"Stereo Mix"** again → Click **"Set as Default Device"**
8. Click **"OK"** to close the window
9. **Refresh the Streamlit app** (Ctrl+F5 in browser)

## Testing Stereo Mix

After enabling:

```powershell
python integrations/audio_device_helper.py
```

You should see device [15] Stereo Mix listed and working.

## Using the App

1. **Start the app:**
   ```powershell
   streamlit run ui/streamlit_app.py
   ```

2. **Go to "Join Live Meeting" tab**

3. **Select audio device:**
   - Look for "Stereo Mix" in the dropdown
   - Should show green checkmark if found

4. **Enter meeting details:**
   - Choose platform (Google Meet or Zoom)
   - Paste meeting URL
   - Set duration

5. **Click "Join Meeting Now"**
   - Browser window will open
   - Bot joins as "AI Meeting Assistant Bot"
   - Transcription happens automatically

## Troubleshooting

### "Stereo Mix not showing"
- Make sure to enable "Show Disabled Devices"
- Some computers don't have Stereo Mix
- **Alternative:** Install VB-CABLE from https://vb-audio.com/Cable/

### "Invalid device error"
- Refresh the Streamlit app after enabling Stereo Mix
- Try restarting your computer
- Select a different device from the dropdown

### "Browser doesn't open"
- Run: `playwright install chromium`
- Check if you have internet connection

### "Can't join Google Meet"
- You may need to log in manually when browser opens
- Bot waits 60 seconds for you to log in

## What's Different Now

✅ **Thread-based execution** - No more asyncio conflicts
✅ **Device selection UI** - Choose audio device in the app
✅ **Better error messages** - Clear instructions when something fails
✅ **Device validation** - Button disabled until device is selected

## Testing Quickly

Want to test without a real meeting?

1. Create a Google Meet: https://meet.google.com/
2. Click "New meeting"
3. Copy the link
4. Paste in the app
5. Set duration to 2-3 minutes
6. Join and watch the bot appear!

---

**Still having issues?** Check [MEETING_BOT_GUIDE.md](MEETING_BOT_GUIDE.md) for detailed troubleshooting.
