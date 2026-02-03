"""
Configuration loader for KBLI RAG Classifier
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
CLASSIFIER_MODEL = "gpt-4o-mini"  # Use mini for cost efficiency
INTENT_SPLITTER_MODEL = "gpt-4o-mini"

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# RAG Settings
TOP_K_RESULTS = 5
BATCH_SIZE = 10  # Micro-batch size for Excel processing

# Sampling Mode (for development)
SAMPLE_MODE = True
SAMPLE_LIMIT = 20  # Only process first N entries when ingesting
