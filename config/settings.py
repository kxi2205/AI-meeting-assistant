"""
Configuration settings for AI Meeting Assistant
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MEETINGS_DIR = DATA_DIR / "meetings"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
CHROMADB_DIR = DATA_DIR / "chromadb"

# Create directories if they don't exist
for directory in [DATA_DIR, MEETINGS_DIR, TRANSCRIPTS_DIR, CHROMADB_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "meeting_assistant")

# Whisper Configuration
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # cpu or cuda

# Groq Configuration
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "2000"))

# RAG Configuration
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model

# Audio Processing
MAX_AUDIO_SIZE_MB = int(os.getenv("MAX_AUDIO_SIZE_MB", "100"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validate required settings
if not GROQ_API_KEY:
    print("⚠️  WARNING: GROQ_API_KEY not set in .env file")
if not MONGODB_URI:
    print("⚠️  WARNING: MONGODB_URI not set in .env file")
