"""ASGI entry point for the Clinic NL2SQL application.

Usage:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

from backend.server import app, main


if __name__ == "__main__":
    main()