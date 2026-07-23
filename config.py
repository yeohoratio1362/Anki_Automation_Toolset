import os
from dotenv import load_dotenv

# Loads variables from .env

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Core Configurations
DB_PATH = os.getenv("ANKI_DB_PATH", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Performance Script Variables
MIN_REVIEW_COUNT = int(os.getenv("MIN_REVIEW_COUNT", 10))
FAIL_RATE_THRESHOLD = float(os.getenv("FAIL_RATE_THRESHOLD", 0.3))
EASY_RATE_THRESHOLD = float(os.getenv("EASY_RATE_THRESHOLD", 0.1))
SLOW_THRESHOLD_SECONDS = float(os.getenv("SLOW_THRESHOLD_SECONDS", 15))
FAST_THRESHOLD_SECONDS = float(os.getenv("FAST_THRESHOLD_SECONDS", 1))

# Tag Identifiers
TAG_DIFFICULT = os.getenv("TAG_DIFFICULT", "difficult_card")
TAG_EASY = os.getenv("TAG_EASY", "practised_card")
TAG_SLOW = os.getenv("TAG_SLOW", "slow_card")
TAG_FAST = os.getenv("TAG_FAST", "fast_card")

# Report export Variables
JOURNAL_DIR = os.getenv("JOURNAL_DIR", "")

# MESH Matcher Configurations
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
SIMILARITY_THRESHOLD =os.getenv("SIMILARITY_THRESHOLD", 0.78)
MESH_XML_PATH =os.getenv("MESH_XML_PATH", "desc2026.xml")
CACHE_PATH = os.getenv("CACHE_PATH", "mesh_embeddings_cache.pkl")
HISTORY_FILE = os.getenv("HISTORY_FILE", "mesh_tag_history.json")
