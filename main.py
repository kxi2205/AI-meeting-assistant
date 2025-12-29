"""
AI Meeting Assistant - Main Entry Point
"""
import sys
import os
from pathlib import Path

def main():
    """Main entry point"""
    print("=" * 60)
    print("AI MEETING ASSISTANT")
    print("=" * 60)
    print()
    
    # Check environment
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("GROQ_API_KEY"):
        print("❌ ERROR: GROQ_API_KEY not found!")
        print("Please create a .env file with your Groq API key")
        print()
        print("Get your free API key at: https://console.groq.com")
        print()
        return
    
    if not os.getenv("MONGODB_URI"):
        print("❌ ERROR: MONGODB_URI not found!")
        print("Please add your MongoDB connection string to .env")
        print()
        return
    
    print("✅ Environment configured!")
    print()
    print("Starting Streamlit UI...")
    print("-" * 60)
    print()
    
    # Run Streamlit
    import streamlit.web.cli as stcli
    ui_path = Path(__file__).parent / "ui" / "streamlit_app.py"
    
    sys.argv = ["streamlit", "run", str(ui_path)]
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()
