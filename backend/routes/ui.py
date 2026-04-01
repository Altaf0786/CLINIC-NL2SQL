"""Custom clinic UI route — serves the branded frontend."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
_INDEX_HTML = (_FRONTEND_DIR / "index.html").read_text()


def register_ui_routes(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def clinic_ui() -> str:
        return _INDEX_HTML
