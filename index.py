"""Vercel entrypoint: Vercel loads the Flask `app` defined here (see pyproject.toml)."""
from app import create_app

app = create_app()
