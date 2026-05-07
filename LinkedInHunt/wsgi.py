"""
WSGI entry point for Hostinger / Passenger / gunicorn deployment.

Hostinger looks for a callable named `application` in this file.
"""

from app import app as application  # noqa: F401

if __name__ == "__main__":
    application.run()
