import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fashion-trend-forecasting-2024')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    # Optional AI API keys
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

    # Cache TTL in seconds
    CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))

    # Number of results per source
    MAX_RESULTS = int(os.environ.get('MAX_RESULTS', '50'))
