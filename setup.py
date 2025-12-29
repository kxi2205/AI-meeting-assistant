#!/usr/bin/env python3
"""
AI Meeting Assistant - Setup Script
Automates initial project setup
"""

import os
import sys
from pathlib import Path

def create_directory_structure():
    """Create all necessary directories"""
    print("📁 Creating directory structure...")
    
    directories = [
        "config",
        "audio_processing",
        "agents",
        "rag",
        "database",
        "integrations",
        "ui",
        "data",
        "data/meetings",
        "data/transcripts",
        "data/chromadb",
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {directory}/")
    
    print()

def create_init_files():
    """Create __init__.py files"""
    print("📝 Creating __init__.py files...")
    
    init_files = {
        "config/__init__.py": '"""Configuration module"""\nfrom .settings import *\n',
        "audio_processing/__init__.py": '"""Audio processing module"""\nfrom .transcriber import AudioTranscriber\n',
        "agents/__init__.py": '"""AI agents module"""\nfrom .summary_agent import SummaryAgent\nfrom .action_item_agent import ActionItemAgent\n',
        "rag/__init__.py": '"""RAG module"""\nfrom .vector_store import VectorStore\n',
        "database/__init__.py": '"""Database module"""\nfrom .mongodb_client import db, MeetingDatabase\n',
        "integrations/__init__.py": '"""Integrations module"""\n',
        "ui/__init__.py": '"""UI module"""\n',
    }
    
    for filepath, content in init_files.items():
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  ✓ {filepath}")
    
    print()

def create_env_file():
    """Create .env file from example"""
    print("🔑 Setting up environment file...")
    
    if Path(".env").exists():
        print("  ℹ️  .env already exists, skipping")
    else:
        if Path(".env.example").exists():
            # Copy .env.example to .env
            with open(".env.example", 'r') as src:
                content = src.read()
            with open(".env", 'w') as dst:
                dst.write(content)
            print("  ✓ Created .env from .env.example")
            print("  ⚠️  IMPORTANT: Edit .env and add your API keys!")
        else:
            print("  ❌ .env.example not found")
    
    print()

def check_dependencies():
    """Check if required dependencies are available"""
    print("🔍 Checking dependencies...")
    
    # Check Python version
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"  ❌ Python 3.8+ required (found {version.major}.{version.minor})")
        return False
    
    # Check pip
    try:
        import pip
        print(f"  ✓ pip installed")
    except ImportError:
        print("  ❌ pip not found")
        return False
    
    # Check FFmpeg
    import subprocess
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              timeout=5)
        if result.returncode == 0:
            print("  ✓ FFmpeg installed")
        else:
            print("  ❌ FFmpeg not working properly")
            return False
    except FileNotFoundError:
        print("  ❌ FFmpeg not found")
        print("     Install: brew install ffmpeg (macOS)")
        print("     Install: sudo apt install ffmpeg (Ubuntu)")
        return False
    except Exception as e:
        print(f"  ⚠️  Could not check FFmpeg: {e}")
    
    print()
    return True

def install_requirements():
    """Install Python requirements"""
    print("📦 Installing Python packages...")
    
    if not Path("requirements.txt").exists():
        print("  ❌ requirements.txt not found")
        return False
    
    import subprocess
    
    print("  This may take 5-10 minutes...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("  ✓ All packages installed successfully")
            return True
        else:
            print("  ❌ Installation failed:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def verify_setup():
    """Verify the setup is complete"""
    print("✅ Verifying setup...")
    
    issues = []
    
    # Check .env
    if not Path(".env").exists():
        issues.append("  ❌ .env file not found")
    else:
        print("  ✓ .env file exists")
    
    # Check core files
    required_files = [
        "config/settings.py",
        "database/mongodb_client.py",
        "audio_processing/transcriber.py",
        "agents/summary_agent.py",
        "agents/action_item_agent.py",
        "rag/vector_store.py",
        "ui/streamlit_app.py",
    ]
    
    for filepath in required_files:
        if Path(filepath).exists():
            print(f"  ✓ {filepath}")
        else:
            issues.append(f"  ❌ Missing: {filepath}")
    
    print()
    
    if issues:
        print("⚠️  Setup incomplete:")
        for issue in issues:
            print(issue)
        return False
    
    return True

def print_next_steps():
    """Print next steps for the user"""
    print("\n" + "="*60)
    print("🎉 Setup Complete!")
    print("="*60)
    print()
    print("Next steps:")
    print()
    print("1. Edit .env file with your API keys:")
    print("   - Get Groq API key: https://console.groq.com")
    print("   - Get MongoDB URI: https://mongodb.com/cloud/atlas")
    print()
    print("2. Test the installation:")
    print("   python -c \"from config import settings; print('✓ Config OK')\"")
    print()
    print("3. Run the application:")
    print("   streamlit run ui/streamlit_app.py")
    print("   or")
    print("   python main.py")
    print()
    print("4. Upload a test meeting and verify everything works!")
    print()
    print("For detailed instructions, see SETUP_GUIDE.md")
    print("For quick start, see QUICKSTART.md")
    print()

def main():
    """Main setup function"""
    print()
    print("="*60)
    print("AI MEETING ASSISTANT - AUTOMATED SETUP")
    print("="*60)
    print()
    
    # Check if we're in the right directory
    if not Path("requirements.txt").exists():
        print("❌ Error: requirements.txt not found")
        print("Please run this script from the project root directory")
        sys.exit(1)
    
    # Run setup steps
    steps = [
        ("Checking dependencies", check_dependencies),
        ("Creating directories", create_directory_structure),
        ("Creating __init__.py files", create_init_files),
        ("Setting up .env file", create_env_file),
    ]
    
    for step_name, step_func in steps:
        print(f"Running: {step_name}")
        result = step_func()
        if result is False:
            print(f"\n❌ Setup failed at: {step_name}")
            sys.exit(1)
    
    # Ask about installing requirements
    print("Would you like to install Python packages now?")
    print("(This will run: pip install -r requirements.txt)")
    response = input("Install now? (y/n): ").lower().strip()
    
    if response == 'y':
        if not install_requirements():
            print("\n⚠️  Package installation failed")
            print("You can try manually: pip install -r requirements.txt")
    else:
        print("\nSkipping package installation")
        print("Install later with: pip install -r requirements.txt")
    
    print()
    
    # Verify setup
    if verify_setup():
        print_next_steps()
    else:
        print("\n⚠️  Setup verification failed")
        print("Please check the issues above and fix them")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
