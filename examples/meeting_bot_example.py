"""
Meeting Bot Example - Demonstration Script
==========================================
This script demonstrates how to use the meeting bot to join live meetings
and integrate with the existing AI Meeting Assistant pipeline.

Examples included:
1. Basic meeting join and transcription
2. Custom configuration
3. Full workflow with analysis
4. Error handling
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.meeting_bot import join_and_capture_audio, join_and_capture_audio_sync, MeetingConfig, MeetingBot
from audio_processing.transcriber import AudioTranscriber
from agents.summary_agent import SummaryAgent
from agents.action_item_agent import ActionItemAgent


# ============================================================================
# Example 1: Basic Usage (Synchronous)
# ============================================================================

def example_basic_sync():
    """
    Simplest usage: Join meeting, transcribe, get results
    """
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Synchronous Usage")
    print("="*60 + "\n")
    
    # Join Zoom meeting
    result = join_and_capture_audio_sync(
        url="https://zoom.us/j/123456789?pwd=yourpassword",
        platform="zoom",
        duration_minutes=30  # Stop after 30 minutes
    )
    
    # Access results
    print(f"\n📊 Meeting Results:")
    print(f"   Platform: {result['platform']}")
    print(f"   Chunks transcribed: {result['total_chunks']}")
    print(f"   Transcript saved: {result['transcript_path']}")
    print(f"\n📝 Full Transcript:\n{result['full_transcript']}")


# ============================================================================
# Example 2: Async Usage with Google Meet
# ============================================================================

async def example_async_google_meet():
    """
    Async usage for Google Meet
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: Async Google Meet")
    print("="*60 + "\n")
    
    result = await join_and_capture_audio(
        url="https://meet.google.com/abc-defg-hij",
        platform="google_meet",
        duration_minutes=45
    )
    
    # Process each chunk individually
    print("\n📊 Processing individual chunks:\n")
    for chunk in result['chunks']:
        print(f"Chunk {chunk['chunk_number']} ({chunk['timestamp']}):")
        print(f"  {chunk['text'][:100]}...")
        print()
    
    return result


# ============================================================================
# Example 3: Custom Configuration
# ============================================================================

async def example_custom_config():
    """
    Use custom configuration for specific requirements
    """
    print("\n" + "="*60)
    print("EXAMPLE 3: Custom Configuration")
    print("="*60 + "\n")
    
    # Create custom configuration
    config = MeetingConfig(
        meeting_url="https://zoom.us/j/987654321",
        platform="zoom",
        duration_minutes=120,      # 2 hour meeting
        chunk_duration=20,         # Transcribe every 20 seconds (faster feedback)
        sample_rate=16000,         # Standard Whisper sample rate
        channels=1,                # Mono audio
        mute_on_join=True,         # Mute bot microphone
        disable_camera=True        # No video
    )
    
    # Use custom Whisper model (larger for better accuracy)
    transcriber = AudioTranscriber(
        model_name="medium",  # Better accuracy than base
        device="cuda"         # Use GPU if available
    )
    
    # Create and run bot with custom settings
    bot = MeetingBot(config, transcriber)
    result = await bot.join_meeting()
    
    print(f"\n✅ Custom config meeting complete")
    print(f"   Used model: {transcriber.model_name}")
    print(f"   Chunks: {result['total_chunks']}")
    
    return result


# ============================================================================
# Example 4: Full Workflow with Analysis
# ============================================================================

async def example_full_workflow():
    """
    Complete workflow: Join → Transcribe → Analyze → Display
    """
    print("\n" + "="*60)
    print("EXAMPLE 4: Full Workflow with Analysis")
    print("="*60 + "\n")
    
    # Step 1: Join meeting and transcribe
    print("🎥 Step 1: Joining meeting and transcribing...")
    result = await join_and_capture_audio(
        url="https://zoom.us/j/123456789",
        platform="zoom",
        duration_minutes=30
    )
    
    transcript = result['full_transcript']
    print(f"✅ Transcription complete: {len(transcript)} characters\n")
    
    # Step 2: Generate summary with existing agent
    print("📋 Step 2: Generating summary...")
    summary_agent = SummaryAgent()
    summary = summary_agent.generate_summary(transcript)
    print(f"✅ Summary generated\n")
    
    # Step 3: Extract action items
    print("✅ Step 3: Extracting action items...")
    action_agent = ActionItemAgent()
    action_items = action_agent.extract_action_items(transcript)
    print(f"✅ {len(action_items)} action items extracted\n")
    
    # Step 4: Display results
    print("\n" + "="*60)
    print("MEETING ANALYSIS RESULTS")
    print("="*60 + "\n")
    
    print("📝 SUMMARY:")
    print("-" * 60)
    print(summary)
    print()
    
    print("✅ ACTION ITEMS:")
    print("-" * 60)
    for i, item in enumerate(action_items, 1):
        print(f"{i}. {item}")
    print()
    
    print("📄 FULL TRANSCRIPT:")
    print("-" * 60)
    print(transcript[:500] + "..." if len(transcript) > 500 else transcript)
    print()
    
    return {
        'transcript': transcript,
        'summary': summary,
        'action_items': action_items,
        'meeting_data': result
    }


# ============================================================================
# Example 5: Error Handling
# ============================================================================

async def example_error_handling():
    """
    Demonstrate proper error handling
    """
    print("\n" + "="*60)
    print("EXAMPLE 5: Error Handling")
    print("="*60 + "\n")
    
    try:
        # Invalid URL
        result = await join_and_capture_audio(
            url="not-a-valid-url",
            platform="zoom"
        )
    except ValueError as e:
        print(f"❌ Caught ValueError: {e}")
    
    try:
        # Unsupported platform
        result = await join_and_capture_audio(
            url="https://example.com",
            platform="microsoft_teams"  # Not supported
        )
    except ValueError as e:
        print(f"❌ Caught ValueError: {e}")
    
    try:
        # Valid meeting but might fail to join
        result = await join_and_capture_audio(
            url="https://zoom.us/j/999999999",  # Invalid meeting ID
            platform="zoom",
            duration_minutes=5
        )
    except Exception as e:
        print(f"❌ Caught Exception: {e}")
    
    print("\n✅ Error handling demonstrated")


# ============================================================================
# Example 6: Real-time Processing
# ============================================================================

async def example_realtime_processing():
    """
    Process transcription chunks in real-time as they arrive
    """
    print("\n" + "="*60)
    print("EXAMPLE 6: Real-time Processing")
    print("="*60 + "\n")
    
    print("Note: This is a conceptual example showing how to extend")
    print("the meeting_bot.py with real-time callbacks.\n")
    
    # Simulated real-time callback
    def on_chunk_transcribed(chunk_data):
        """Called whenever a chunk is transcribed"""
        print(f"\n🔔 Real-time notification:")
        print(f"   Chunk {chunk_data['chunk_number']}")
        print(f"   Text: {chunk_data['text'][:80]}...")
        
        # Could send to:
        # - Websocket for live dashboard
        # - Slack channel
        # - Database for immediate storage
        # - Email if keywords detected
    
    print("To implement:")
    print("1. Modify MeetingBot._transcription_loop() to accept callback")
    print("2. Call callback after each transcription")
    print("3. Pass custom callback when creating MeetingBot")
    print("\nExample code:")
    print("""
    bot = MeetingBot(config)
    bot.on_chunk_callback = on_chunk_transcribed
    result = await bot.join_meeting()
    """)


# ============================================================================
# Example 7: CLI Interface
# ============================================================================

def example_cli():
    """
    Command-line interface for quick testing
    """
    print("\n" + "="*60)
    print("EXAMPLE 7: CLI Interface")
    print("="*60 + "\n")
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Join live meeting and transcribe")
    parser.add_argument("url", help="Meeting URL")
    parser.add_argument("platform", choices=["zoom", "google_meet"], help="Platform type")
    parser.add_argument("--duration", type=int, default=60, help="Max duration (minutes)")
    parser.add_argument("--model", default="base", help="Whisper model (tiny/base/small/medium/large)")
    parser.add_argument("--analyze", action="store_true", help="Run analysis after transcription")
    
    # Example usage (don't actually parse in this demo)
    print("Usage:")
    print('  python examples/meeting_bot_example.py "https://zoom.us/j/123" zoom --duration 30 --analyze')
    print()
    
    # Simulated
    args = argparse.Namespace(
        url="https://zoom.us/j/123456789",
        platform="zoom",
        duration=30,
        model="base",
        analyze=True
    )
    
    print(f"Would join: {args.url}")
    print(f"Platform: {args.platform}")
    print(f"Duration: {args.duration} minutes")
    print(f"Model: {args.model}")
    print(f"Analyze: {args.analyze}")


# ============================================================================
# Main Menu
# ============================================================================

async def main():
    """
    Interactive menu to run different examples
    """
    print("\n" + "="*60)
    print("MEETING BOT EXAMPLES")
    print("="*60)
    print()
    print("Choose an example to run:")
    print()
    print("1. Basic synchronous usage (Zoom)")
    print("2. Async usage with Google Meet")
    print("3. Custom configuration")
    print("4. Full workflow with analysis")
    print("5. Error handling demonstration")
    print("6. Real-time processing (conceptual)")
    print("7. CLI interface example")
    print()
    print("0. Exit")
    print()
    
    choice = input("Enter choice (0-7): ").strip()
    
    if choice == "1":
        # Note: Replace with actual meeting URL to test
        print("\n⚠️  Replace URL with actual meeting link to test")
        # example_basic_sync()
    
    elif choice == "2":
        print("\n⚠️  Replace URL with actual meeting link to test")
        # await example_async_google_meet()
    
    elif choice == "3":
        print("\n⚠️  Replace URL with actual meeting link to test")
        # await example_custom_config()
    
    elif choice == "4":
        print("\n⚠️  Replace URL with actual meeting link to test")
        # await example_full_workflow()
    
    elif choice == "5":
        await example_error_handling()
    
    elif choice == "6":
        await example_realtime_processing()
    
    elif choice == "7":
        example_cli()
    
    elif choice == "0":
        print("\n👋 Goodbye!")
        return
    
    else:
        print("\n❌ Invalid choice")


# ============================================================================
# Quick Start Guide
# ============================================================================

def print_quickstart():
    """
    Print quick start instructions
    """
    print("\n" + "="*60)
    print("MEETING BOT - QUICK START")
    print("="*60 + "\n")
    
    print("1. INSTALL DEPENDENCIES")
    print("-" * 60)
    print("   pip install playwright sounddevice scipy")
    print("   playwright install chromium")
    print()
    
    print("2. SETUP AUDIO CAPTURE")
    print("-" * 60)
    print("   Windows: Install VB-CABLE (https://vb-audio.com/Cable/)")
    print("   macOS:   brew install blackhole-2ch")
    print("   Linux:   pactl load-module module-loopback")
    print()
    print("   Run audio device helper:")
    print("   python integrations/audio_device_helper.py")
    print()
    
    print("3. BASIC USAGE")
    print("-" * 60)
    print("""
from integrations.meeting_bot import join_and_capture_audio_sync

result = join_and_capture_audio_sync(
    url="https://zoom.us/j/YOUR_MEETING_ID",
    platform="zoom",
    duration_minutes=30
)

print(result['full_transcript'])
    """)
    
    print("4. COMMAND LINE")
    print("-" * 60)
    print('   python integrations/meeting_bot.py "URL" zoom 30')
    print()
    
    print("5. DOCUMENTATION")
    print("-" * 60)
    print("   See MEETING_BOT_GUIDE.md for complete documentation")
    print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quickstart":
        print_quickstart()
    else:
        asyncio.run(main())
