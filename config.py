import os
import warnings
from dotenv import load_dotenv

load_dotenv()


class Config:
    _default_secret = 'fashion-trend-forecasting-dev-key-change-me'
    _secret_key = os.environ.get('SECRET_KEY', '')

    if not _secret_key:
        if os.environ.get('FLASK_ENV', 'development') == 'production':
            raise RuntimeError(
                'SECRET_KEY environment variable must be set in production. '
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        warnings.warn(
            'SECRET_KEY is not set. Using an insecure default — set SECRET_KEY before deploying.',
            UserWarning,
            stacklevel=1,
        )
        _secret_key = _default_secret

    SECRET_KEY  = _secret_key
    DEBUG       = os.environ.get('DEBUG', 'False').lower() == 'true'

    # AI API keys — all optional; falls back to Ollama then rule-based
    GROQ_API_KEY   = os.environ.get('GROQ_API_KEY', '')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

    # TikTok Research API credentials — optional; enables live hashtag data
    # Apply at https://developers.tiktok.com/products/research-api/
    TIKTOK_CLIENT_KEY    = os.environ.get('TIKTOK_CLIENT_KEY', '')
    TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET', '')

    # Pinterest API v5 access token — optional; enables pin search
    # Create an app at https://developers.pinterest.com/
    PINTEREST_ACCESS_TOKEN = os.environ.get('PINTEREST_ACCESS_TOKEN', '')

    # Ollama local model config
    OLLAMA_HOST  = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3')

    # Cache TTL in seconds
    CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))

    # Number of results per source
    MAX_RESULTS = int(os.environ.get('MAX_RESULTS', '50'))
