import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'trend-forecasting-secret-2024')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    # Optional API keys (all have free tiers or no auth needed)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '')
    REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID', '')
    REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET', '')
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

    # Cache settings
    CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))  # 5 minutes

    # Data fetch limits
    MAX_RESULTS = int(os.environ.get('MAX_RESULTS', '50'))
