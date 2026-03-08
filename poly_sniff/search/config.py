import os
from dotenv import load_dotenv

load_dotenv()

RESEARCHTOOLS_URL = os.getenv('RESEARCHTOOLS_URL', 'http://localhost:8788')
POLYMARKET_GAMMA_API = 'https://gamma-api.polymarket.com'
DEFAULT_TOP_N = 5
DEFAULT_MIN_RELEVANCE = 50
MAX_CANDIDATES = 35
