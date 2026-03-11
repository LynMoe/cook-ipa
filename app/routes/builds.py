"""
Build routes — no database, reads from JSON files.
"""
import os
import logging
from pathlib import Path
from flask import Blueprint, jsonify, request, Response, stream_with_context, send_file

from app.services.build_store import get_store
from config import Config

builds_bp = Blueprint("builds", __name__)
log = logging.getLogger(__name__)


def _base_url() -> str:
    return Config.SERVER_BASE_URL.rstrip("/")


@builds_bp.route("/builds", methods=["GET"])
def list_builds():
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    store    = get_store()
    builds, total = store.list_all(page=page, per_page=per_page)
    base = _base_url()
    return jsonify({
        "builds": [store.to_api_dict(b, base) for b in builds],
        "total":  total,
        "page":   page,
    })


@builds_bp.route("/builds/<build_uuid>", methods=["GET"])
def get_build(build_uuid: str):
    store = get_store()
    meta  = store.get(build_uuid)
    if not meta:
        return jsonify({"error": "Build not found"}), 404
    return jsonify({"build": store.to_api_dict(meta, _base_url())})


@builds_bp.route("/builds/<build_uuid>", methods=["DELETE"])
def delete_build(build_uuid: str):
    from app.services.s3_storage import delete_build_objects
    store = get_store()
    if not store.get(build_uuid):
        return jsonify({"error": "Build not found"}), 404
    delete_build_objects(build_uuid)
    store.delete(build_uuid)
    return jsonify({"success": True})


@builds_bp.route("/builds/<build_uuid>/logs", methods=["GET"])
def get_build_logs(build_uuid: str):
    store    = get_store()
    meta     = store.get(build_uuid)
    if not meta:
        return jsonify({"error": "Build not found"}), 404
    since_id = request.args.get("since_id", 0, type=int)
    logs     = store.read_logs(build_uuid, since_id)
    return jsonify({"status": meta.get("status"), "logs": logs})


@builds_bp.route("/builds/<build_uuid>/logs/stream", methods=["GET"])
def stream_build_logs(build_uuid: str):
    import time, json
    store = get_store()

    def generate():
        last_id = 0
        terminal = {"done", "failed"}
        while True:
            meta = store.get(build_uuid)
            if not meta:
                break
            for entry in store.read_logs(build_uuid, last_id):
                last_id = entry["id"]
                yield f"data: {json.dumps(entry)}\n\n"
            if meta.get("status") in terminal:
                yield f"event: done\ndata: {json.dumps({'status': meta['status']})}\n\n"
                break
            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@builds_bp.route("/build-icon/<build_uuid>", methods=["GET"])
def serve_icon(build_uuid: str):
    store = get_store()
    meta  = store.get(build_uuid)  # Now includes UUID validation
    
    if not meta or not meta.get("icon_path"):
        return jsonify({"error": "Not found"}), 404
    
    icon_path = Path(meta["icon_path"])
    
    # Validate icon path is within builds directory
    builds_dir = Path(Config.BUILDS_DIR).resolve()
    try:
        resolved_icon = icon_path.resolve()
        if not str(resolved_icon).startswith(str(builds_dir)):
            log.error(f"Icon path traversal attempt: {icon_path}")
            return jsonify({"error": "Forbidden"}), 403
    except Exception as e:
        log.error(f"Icon path resolution failed: {e}")
        return jsonify({"error": "Invalid path"}), 400
    
    if not icon_path.exists():
        return jsonify({"error": "Not found"}), 404
    
    return send_file(str(icon_path), mimetype="image/png")


@builds_bp.route("/builds/cleanup", methods=["POST"])
def cleanup_builds():
    from datetime import timedelta, datetime
    from app.services.s3_storage import delete_build_objects
    days   = request.json.get("days", 30) if request.is_json else 30
    cutoff = datetime.utcnow() - timedelta(days=days)
    store  = get_store()
    builds, _ = store.list_all(per_page=9999)
    removed = 0
    for b in builds:
        if b.get("status") in ("done", "failed"):
            try:
                created = datetime.fromisoformat(b["created_at"])
                if created < cutoff:
                    delete_build_objects(b["uuid"])
                    store.delete(b["uuid"])
                    removed += 1
            except Exception:
                log.exception("Failed to remove build %s during cleanup", b.get("uuid"))
    return jsonify({"success": True, "builds_removed": removed})
