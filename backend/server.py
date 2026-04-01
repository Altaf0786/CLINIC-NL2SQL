"""FastAPI application factory.

Wires the VannaFastAPIServer with security middleware, static file
serving for the custom clinic frontend, and replaces Vanna's built-in
index route with our branded UI.
"""

from pathlib import Path

from fastapi.staticfiles import StaticFiles
from vanna.servers.fastapi import VannaFastAPIServer

from backend.config.settings import settings
from backend.middleware.request_handler import security_and_logging_middleware
from backend.routes.ui import register_ui_routes
from backend.services.agent_factory import agent

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def build_server_config() -> dict:
    return {
        "cors": {
            "enabled": True,
            "allow_origins": settings.ALLOWED_ORIGINS,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type", "Cookie"],
        },
    }


# Create the Vanna FastAPI server and the ASGI app
server = VannaFastAPIServer(agent, config=build_server_config())
app = server.create_app()
app.title = "Clinic NL2SQL API"
app.version = "1.0.0"
app.description = "Vanna-powered clinic analytics agent"

# Remove Vanna's built-in "/" route so our custom clinic UI takes over.
# Vanna registers its own index inside create_app(); we strip it here.
app.routes[:] = [
    route for route in app.routes
    if not (hasattr(route, "path") and route.path == "/")
]

# Serve frontend static assets (CSS, JS) at /static/
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Custom UI route overrides Vanna's default index
register_ui_routes(app)

# Security & logging middleware
app.middleware("http")(security_and_logging_middleware)


def main() -> None:
    server.run(
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
