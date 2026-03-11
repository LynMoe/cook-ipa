"""
SPA and static serving. SPA dir is resolved at runtime via Config.get_spa_dir() (override with SPA_DIR env).
"""
from flask import Blueprint, send_from_directory


def _spa_dir():
    """Resolve SPA directory at request time (dynamic load)."""
    from config import Config
    return Config.get_spa_dir()


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return send_from_directory(_spa_dir(), "index.html")


@main_bp.route("/<path:path>")
def spa_fallback(path: str):
    if path.startswith("api/"):
        return {"error": "Not found"}, 404
    spa_dir = _spa_dir()
    file_path = spa_dir / path
    if file_path.is_file():
        return send_from_directory(spa_dir, path)
    return send_from_directory(spa_dir, "index.html")
