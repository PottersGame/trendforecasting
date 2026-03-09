#!/usr/bin/env python3
"""Main entry point for the Fashion Trend Forecasting application.

For development only.  In production, serve with a WSGI server, e.g.:
    gunicorn "app:create_app()" --workers 2
"""

import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    port  = int(os.environ.get('PORT', '5000'))
    app.run(debug=debug, host='0.0.0.0', port=port)
