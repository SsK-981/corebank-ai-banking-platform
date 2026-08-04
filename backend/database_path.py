"""Small helper kept separate to avoid configuration/database import cycles."""

from pathlib import Path


def default_sqlite_url() -> str:
    path = Path(__file__).resolve().parent / "fintech_agent.db"
    return f"sqlite:///{path.as_posix()}"
