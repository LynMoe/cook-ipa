import uuid
import logging
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

import requests as http_requests
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from app.services.build_store import get_store
from app.services.build_pipeline import start_pipeline

upload_bp = Blueprint("upload", __name__)
log = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 300  # seconds
_MAX_IPA_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB guard


@upload_bp.route("/upload", methods=["POST"])
def upload_ipa():
    if "file" not in request.files:
        return jsonify({"error": "No file field"}), 400
    f = request.files["file"]
    if not f or not f.filename or not f.filename.lower().endswith(".ipa"):
        return jsonify({"error": "Only .ipa files accepted"}), 400

    original_filename = secure_filename(f.filename)
    build_uuid = str(uuid.uuid4())

    # Save to builds/<uuid>/ directory
    store = get_store()
    build_dir = store.build_dir(build_uuid)
    build_dir.mkdir(parents=True, exist_ok=True)
    ipa_path = build_dir / f"original_{original_filename}"
    f.save(str(ipa_path))

    file_size = ipa_path.stat().st_size
    log.info("Received IPA: %s (%.1f MB)", original_filename, file_size / 1048576)

    meta = store.create(build_uuid, original_filename, str(ipa_path))
    store.append_log(build_uuid, f"IPA received: {original_filename} ({file_size/1048576:.1f} MB)")

    start_pipeline(current_app._get_current_object(), build_uuid)

    return jsonify({
        "success": True,
        "build": meta,
        "message": "IPA received. Processing started.",
    }), 202


@upload_bp.route("/upload-url", methods=["POST"])
def upload_ipa_from_url():
    body = request.get_json(silent=True) or {}
    ipa_url = (body.get("url") or "").strip()

    if not ipa_url:
        return jsonify({"error": "url field is required"}), 400

    parsed = urlparse(ipa_url)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    # Derive a safe filename from the URL path, fallback to "app.ipa"
    url_path = parsed.path.rstrip("/")
    raw_name = url_path.split("/")[-1] if url_path else "app.ipa"
    if not raw_name.lower().endswith(".ipa"):
        raw_name = raw_name + ".ipa"
    original_filename = secure_filename(raw_name) or "app.ipa"

    build_uuid = str(uuid.uuid4())
    store = get_store()
    build_dir = store.build_dir(build_uuid)
    build_dir.mkdir(parents=True, exist_ok=True)
    ipa_path = build_dir / f"original_{original_filename}"

    log.info("Downloading IPA from URL: %s", ipa_url)
    try:
        with http_requests.get(
            ipa_url,
            stream=True,
            timeout=_DOWNLOAD_TIMEOUT,
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            downloaded = 0
            with open(ipa_path, "wb") as out_f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > _MAX_IPA_SIZE:
                            ipa_path.unlink(missing_ok=True)
                            return jsonify({"error": "IPA file exceeds 2 GB limit"}), 400
                        out_f.write(chunk)
    except http_requests.exceptions.RequestException as e:
        ipa_path.unlink(missing_ok=True)
        log.warning("Failed to download IPA from %s: %s", ipa_url, e)
        return jsonify({"error": f"Failed to download IPA: {e}"}), 400

    file_size = ipa_path.stat().st_size
    log.info("Downloaded IPA: %s (%.1f MB)", original_filename, file_size / 1048576)

    meta = store.create(build_uuid, original_filename, str(ipa_path))
    store.append_log(
        build_uuid,
        f"IPA downloaded from URL: {ipa_url} — {original_filename} ({file_size/1048576:.1f} MB)",
    )

    start_pipeline(current_app._get_current_object(), build_uuid)

    return jsonify({
        "success": True,
        "build": meta,
        "message": "IPA downloaded and processing started.",
    }), 202
