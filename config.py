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

    # AI API keys — all optional; falls back through chain then rule-based
    GROQ_API_KEY    = os.environ.get('GROQ_API_KEY', '')
    OPENAI_API_KEY  = os.environ.get('OPENAI_API_KEY', '')
    GEMINI_API_KEY  = os.environ.get('GEMINI_API_KEY', '')  # Google Gemini (free tier)

    # Ollama local model config
    OLLAMA_HOST  = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3')

    # Cache TTL in seconds
    CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))

    # Number of results per source
    MAX_RESULTS = int(os.environ.get('MAX_RESULTS', '50'))

    # API key that protects AI and ingest endpoints from public access.
    # Leave empty to run open (dev mode).  Generate one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(32))"
    APP_API_KEY = os.environ.get('APP_API_KEY', '').strip()

    # How often (in minutes) to automatically ingest data in the background.
    # 0 = disabled.  Recommended: 120 (every 2 hours).
    SCRAPE_INTERVAL_MINUTES = int(os.environ.get('SCRAPE_INTERVAL_MINUTES', '0'))

    # Bootstrap admin account created on first run (optional).
    # Set both to seed an admin user; leave blank to skip.
    ADMIN_EMAIL    = os.environ.get('ADMIN_EMAIL', '').strip()
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip()
