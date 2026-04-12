"""
Audio Device Helper for Meeting Bot
====================================
Utilities to list and configure audio devices for capturing meeting audio.

This module helps users:
1. List available audio input devices
2. Find loopback/virtual cable devices
3. Configure the correct device for meeting capture
"""

import sounddevice as sd
import platform
from typing import List, Dict, Optional


def list_audio_devices() -> List[Dict]:
    """
    List all available audio input devices
    
    Returns:
        List of device info dictionaries
    """
    devices = sd.query_devices()
    input_devices = []
    
    print("\n" + "="*60)
    print("AVAILABLE AUDIO INPUT DEVICES")
    print("="*60 + "\n")
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            input_devices.append({
                'index': i,
                'name': device['name'],
                'channels': device['max_input_channels'],
                'sample_rate': device['default_samplerate']
            })
            
            print(f"[{i}] {device['name']}")
            print(f"    Channels: {device['max_input_channels']}")
            print(f"    Sample Rate: {device['default_samplerate']} Hz")
            print()
    
    return input_devices


def find_loopback_device() -> Optional[int]:
    """
    Attempt to find a loopback/virtual audio device
    
    Common names:
    - Windows: "CABLE Output", "VB-Audio", "Stereo Mix"
    - Mac: "BlackHole", "Loopback"
    - Linux: "Monitor of", "loopback"
    
    Returns:
        Device index if found, None otherwise
    """
    devices = sd.query_devices()
    
    loopback_keywords = [
        'cable', 'vb-audio', 'stereo mix', 'loopback',
        'blackhole', 'monitor of', 'what u hear'
    ]
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            device_name = device['name'].lower()
            for keyword in loopback_keywords:
                if keyword in device_name:
                    print(f"[FOUND] Loopback device: [{i}] {device['name']}")
                    return i
    
    print("[WARN] No loopback device found")
    return None


def test_device(device_index: int, duration: int = 3):
    """
    Test an audio device by recording for a few seconds
    
    Args:
        device_index: Device index to test
        duration: Test duration in seconds
    """
    import numpy as np
    
    print(f"\n[TESTING] Testing device {device_index} for {duration} seconds...")
    print("   (Speak or play audio to see if it's capturing)")
    
    try:
        recording = sd.rec(
            int(duration * 16000),
            samplerate=16000,
            channels=1,
            device=device_index,
            dtype=np.float32
        )
        sd.wait()
        
        # Check if audio was captured
        max_amplitude = np.abs(recording).max()
        avg_amplitude = np.abs(recording).mean()
        
        print(f"\n   Max amplitude: {max_amplitude:.4f}")
        print(f"   Avg amplitude: {avg_amplitude:.4f}")
        
        if max_amplitude > 0.01:
            print("   [OK] Device is capturing audio!")
        else:
            print("   [WARN] No audio detected (silence)")
        
    except Exception as e:
        print(f"   [ERROR] Error testing device: {e}")


def get_device_setup_instructions():
    """
    Print platform-specific setup instructions
    """
    os_name = platform.system()
    
    print("\n" + "="*60)
    print("AUDIO DEVICE SETUP INSTRUCTIONS")
    print("="*60 + "\n")
    
    if os_name == "Windows":
        print("WINDOWS SETUP:")
        print("-" * 60)
        print()
        print("Option 1: Virtual Audio Cable (Recommended)")
        print("  1. Download VB-CABLE from: https://vb-audio.com/Cable/")
        print("  2. Install VB-CABLE")
        print("  3. Right-click speaker icon → Sounds")
        print("  4. Playback tab: Set 'CABLE Input' as default device")
        print("  5. Recording tab: Set 'CABLE Output' as default device")
        print("  6. In browser, audio will route through virtual cable")
        print()
        print("Option 2: Stereo Mix (Built-in)")
        print("  1. Right-click speaker icon → Sounds")
        print("  2. Recording tab → Right-click → Show Disabled Devices")
        print("  3. Enable 'Stereo Mix'")
        print("  4. Set as default recording device")
        print()
        print("Option 3: Use pyaudiowpatch (Advanced)")
        print("  1. pip install pyaudiowpatch")
        print("  2. Modify meeting_bot.py to use pyaudiowpatch instead of sounddevice")
        print()
    
    elif os_name == "Darwin":  # macOS
        print("macOS SETUP:")
        print("-" * 60)
        print()
        print("Option 1: BlackHole (Recommended)")
        print("  1. Install BlackHole: brew install blackhole-2ch")
        print("  2. Open Audio MIDI Setup")
        print("  3. Create Multi-Output Device:")
        print("     - Include your speakers + BlackHole")
        print("  4. Create Aggregate Device:")
        print("     - Include BlackHole as input")
        print("  5. Set Aggregate Device as input in meeting_bot.py")
        print()
        print("Option 2: Loopback by Rogue Amoeba")
        print("  1. Purchase and install Loopback")
        print("  2. Create virtual audio device")
        print("  3. Route browser audio to virtual device")
        print()
    
    else:  # Linux
        print("LINUX SETUP:")
        print("-" * 60)
        print()
        print("PulseAudio:")
        print("  1. Load loopback module:")
        print("     pactl load-module module-loopback")
        print("  2. Use pavucontrol to route audio:")
        print("     - Set browser output to 'Monitor of ...'")
        print()
        print("ALSA:")
        print("  1. Create loopback device in ~/.asoundrc")
        print("  2. Use arecord to capture from loopback")
        print()
    
    print("="*60)
    print()


def configure_meeting_bot_device(device_index: int) -> str:
    """
    Generate code snippet to use specific device in meeting_bot.py
    
    Args:
        device_index: Device index to use
        
    Returns:
        Code snippet as string
    """
    code = f"""
# In meeting_bot.py, modify the _start_audio_capture method:

def _start_audio_capture(self):
    # ... existing code ...
    
    self.audio_stream = sd.InputStream(
        samplerate=self.config.sample_rate,
        channels=self.config.channels,
        callback=audio_callback,
        blocksize=4096,
        dtype=np.float32,
        device={device_index}  # <-- Add this line
    )
"""
    return code


def interactive_setup():
    """
    Interactive CLI to help user configure audio device
    """
    print("\n[SETUP] Meeting Bot Audio Setup Wizard")
    print("="*60 + "\n")
    
    # List devices
    devices = list_audio_devices()
    
    if not devices:
        print("[ERROR] No input devices found!")
        return
    
    # Try to find loopback
    loopback_idx = find_loopback_device()
    
    if loopback_idx is not None:
        print(f"\n[RECOMMENDED] Recommended device: {loopback_idx}")
        test = input("\nTest this device? (y/n): ").lower()
        if test == 'y':
            test_device(loopback_idx)
    else:
        print("\n[WARN] No virtual audio device found")
        get_device_setup_instructions()
        
        print("\nAfter setting up a virtual audio device:")
        print("  1. Restart this script")
        print("  2. Select the device from the list")
        print()
        
        choice = input("Enter device index to test (or 'q' to quit): ")
        if choice.lower() != 'q':
            try:
                idx = int(choice)
                test_device(idx)
            except:
                print("Invalid input")
    
    print("\n" + "="*60)
    print("Setup complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    """
    Run audio device helper
    
    Usage:
        python audio_device_helper.py
    """
    interactive_setup()
