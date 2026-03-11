"""
Device management — Apple API only, no local database.
  GET  /api/devices        — List from Apple API
  POST /api/devices        — Register via Apple API
"""
import logging
from flask import Blueprint, jsonify, request

from app.services.appstore_api import AppStoreConnectClient, AppStoreConnectError
from config import Config

devices_bp = Blueprint("devices", __name__)
log = logging.getLogger(__name__)


def _client():
    return AppStoreConnectClient(
        key_id=Config.APPLE_KEY_ID,
        issuer_id=Config.APPLE_ISSUER_ID,
        private_key_path=Config.APPLE_PRIVATE_KEY_PATH,
    )


@devices_bp.route("/devices", methods=["GET"])
def list_devices():
    try:
        api     = _client()
        devices = api.list_devices(status=None)  # Get all devices (enabled + disabled)
        result  = [
            {
                "apple_device_id": d["id"],
                "udid":     d["attributes"]["udid"],
                "name":     d["attributes"]["name"],
                "platform": d["attributes"]["platform"],
                "status":   d["attributes"]["status"],
            }
            for d in devices
        ]
        return jsonify({"devices": result, "total": len(result)})
    except AppStoreConnectError as e:
        return jsonify({"error": str(e)}), 502


@devices_bp.route("/devices", methods=["POST"])
def register_device():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    udid = (data.get("udid") or "").strip().upper()
    platform = (data.get("platform") or "IOS").upper()

    if not name or not udid:
        return jsonify({"error": "name and udid are required"}), 400

    try:
        api    = _client()
        device = api.register_device(name=name, udid=udid, platform=platform)
        return jsonify({
            "success": True,
            "device": {
                "apple_device_id": device["id"],
                "udid":     device["attributes"]["udid"],
                "name":     device["attributes"]["name"],
                "platform": device["attributes"]["platform"],
                "status":   device["attributes"]["status"],
            },
        }), 201
    except AppStoreConnectError as e:
        if e.status_code == 409:
            # Device already registered — just return success
            return jsonify({"success": True, "message": "Device already registered in Apple Developer"}), 200
        return jsonify({"error": str(e)}), 502
