"""
Profile management — Apple API + local .mobileprovision files, no database.
  GET  /api/profiles         — List from Apple API with local metadata
  GET  /api/profiles/status  — Resolver status (active, latest, coverage, missing_devices)
  GET  /api/profiles/local   — List locally saved .mobileprovision files
  POST /api/profiles/<id>/download  — Download profile from Apple and cache (backend only)
  POST /api/profiles/regenerate     — Regenerate profile (backend only)
  POST /api/profiles/check-update   — Check if active profile needs update (backend only)
"""
import logging
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

from app.services.appstore_api import AppStoreConnectClient, AppStoreConnectError
from app.domain.profile_resolver import ProfileResolver
from config import Config

profiles_bp = Blueprint("profiles", __name__)
log = logging.getLogger(__name__)


def _client():
    return AppStoreConnectClient(
        key_id=Config.APPLE_KEY_ID,
        issuer_id=Config.APPLE_ISSUER_ID,
        private_key_path=Config.APPLE_PRIVATE_KEY_PATH,
    )


@profiles_bp.route("/profiles/status", methods=["GET"])
def profiles_status():
    """
    Return profile resolver status for SPA (read-only).
    Keys: active_path, latest, coverage, missing_devices, enabled_count, error.
    """
    resolver = ProfileResolver()
    return jsonify(resolver.get_status())


@profiles_bp.route("/profiles", methods=["GET"])
def list_profiles():
    """
    List Ad Hoc profiles from Apple API, enriched with local metadata.
    Active profile (current in use) is moved to the top.
    
    Returns profiles from Apple Developer, but adds local metadata if available:
    - If local .mobileprovision exists for a profile, include device UUIDs
    - If not exists, return null for metadata (client can download on demand)
    """
    from app.services.mobileprovision_parser import parse_mobileprovision
    
    try:
        api = _client()
        profiles = api.list_profiles(profile_type="IOS_APP_ADHOC")
        
        # Get currently active profile UUID
        active_profile_path = Config.get_mobileprovision_path()
        active_uuid = None
        if active_profile_path:
            active_metadata = parse_mobileprovision(active_profile_path)
            if active_metadata:
                active_uuid = active_metadata["uuid"]
        
        # Map local files from /tmp cache by UUID
        cache_dir = Config.PROFILE_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        local_map = {}
        for p in cache_dir.glob("*.mobileprovision"):
            metadata = parse_mobileprovision(str(p))
            if metadata:
                # Use UUID as key
                local_map[metadata["uuid"]] = {
                    "file_path": str(p),
                    "uuid": metadata["uuid"],
                    "devices": metadata["devices"],
                    "device_count": len(metadata["devices"]),
                    "bundle_id": metadata["bundle_id"],
                    "expiration_date": metadata["expiration_date"].isoformat() if metadata["expiration_date"] else None,
                    "file_size": p.stat().st_size,
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                }
        
        result = []
        for p in profiles:
            name = p["attributes"]["name"]
            attrs = p["attributes"]
            profile_uuid = attrs.get("uuid")
            
            item = {
                "apple_profile_id": p["id"],
                "name": name,
                "profile_type": attrs["profileType"],
                "platform": attrs["platform"],
                "expiry_date": attrs.get("expirationDate"),
                "state": attrs["profileState"],
                "uuid": profile_uuid,
                "is_active": (profile_uuid == active_uuid),
                "local_metadata": local_map.get(profile_uuid),  # null if not cached locally
            }
            result.append(item)
        
        # Sort: active profile first, then by name
        result.sort(key=lambda x: (not x["is_active"], x["name"]))
        
        return jsonify({"profiles": result, "total": len(result)})
    except AppStoreConnectError as e:
        return jsonify({"error": str(e)}), 502


@profiles_bp.route("/profiles/<profile_id>/download", methods=["POST"])
def download_profile(profile_id: str):
    """
    Download a profile from Apple API and save locally.
    
    Args:
        profile_id: Apple profile ID
    
    Returns:
        {
            "success": bool,
            "profile_path": str,
            "metadata": {...}
        }
    """
    from app.services.mobileprovision_parser import parse_mobileprovision
    from datetime import datetime as _dt
    
    try:
        api = _client()

        profile = api.get_profile(profile_id)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        
        profile_name = profile["attributes"]["name"]
        
        # Download content
        mp_bytes = api.download_profile_content(profile)
        
        # Save to /tmp with Cook-IPA-Auto prefix
        timestamp = _dt.utcnow().strftime('%Y%m%d%H%M%S')
        output_path = str(
            Config.PROFILE_CACHE_DIR / f"Cook-IPA-Auto_{timestamp}.mobileprovision"
        )
        Config.PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(mp_bytes)
        
        # Parse metadata
        metadata = parse_mobileprovision(output_path)
        
        metadata_response = None
        if metadata:
            metadata_response = {
                "uuid": metadata["uuid"],
                "devices": metadata["devices"],
                "device_count": len(metadata["devices"]),
                "bundle_id": metadata["bundle_id"],
                "expiration_date": metadata["expiration_date"].isoformat() if metadata.get("expiration_date") else None,
            }
        
        return jsonify({
            "success": True,
            "profile_path": output_path,
            "metadata": metadata_response,
        })
    except AppStoreConnectError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        log.exception(f"Failed to download profile {profile_id}")
        return jsonify({"error": str(e)}), 500


@profiles_bp.route("/profiles/local", methods=["GET"])
def list_local_profiles():
    """
    List .mobileprovision files in certs/ with full metadata.
    - Parses each file to extract device UUIDs
    - Matches against Apple API profiles
    - Checks for missing devices
    - Flags if regeneration is needed
    """
    from app.services.mobileprovision_parser import (
        parse_mobileprovision,
        match_profile_to_apple_api,
        check_missing_devices,
    )
    
    certs_dir = Path(Config.CERTS_DIR)
    active_path = Config.get_mobileprovision_path()
    
    # Fetch current devices and profiles from Apple API
    try:
        api = _client()
        api_profiles = api.list_profiles(profile_type="IOS_APP_ADHOC")
        api_devices = api.list_devices(platform="IOS", status=None)  # All devices
    except AppStoreConnectError as e:
        log.error(f"Failed to fetch Apple API data: {e}")
        api_profiles = []
        api_devices = []
    
    files = []
    for p in sorted(certs_dir.glob("*.mobileprovision"), key=lambda f: f.stat().st_mtime, reverse=True):
        metadata = parse_mobileprovision(str(p))
        
        if not metadata:
            log.warning(f"Failed to parse {p.name}")
            continue
        
        # Match to Apple API profile
        api_match = match_profile_to_apple_api(metadata, api_profiles)
        
        # Check missing devices
        missing = check_missing_devices(metadata, api_devices)
        
        files.append({
            "filename": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            "active": (str(p) == active_path),
            "metadata": {
                "name": metadata["name"],
                "team_name": metadata["team_name"],
                "bundle_id": metadata["bundle_id"],
                "profile_type": metadata["profile_type"],
                "uuid": metadata["uuid"],
                "expiration_date": metadata["expiration_date"].isoformat() if metadata["expiration_date"] else None,
                "device_count": len(metadata["devices"]),
                "devices": metadata["devices"],
                "certificates": metadata["certificates"],
            },
            "api_match": bool(api_match),
            "api_profile_id": api_match["id"] if api_match else None,
            "missing_devices": [
                {
                    "id": d["id"],
                    "name": d["attributes"]["name"],
                    "udid": d["attributes"]["udid"],
                    "platform": d["attributes"]["platform"],
                    "status": d["attributes"]["status"],
                }
                for d in missing
            ],
            "needs_regeneration": len([d for d in missing if d.get("attributes", {}).get("status") == "ENABLED"]) > 0,
        })
    
    # Filter: only show profiles that match Apple API (unless no API data available)
    if api_profiles:
        files = [f for f in files if f["api_match"]]
    
    return jsonify({
        "profiles": files,
        "active_path": active_path,
        "total_devices": len(api_devices),
        "total_api_profiles": len(api_profiles),
    })


@profiles_bp.route("/profiles/regenerate", methods=["POST"])
def regenerate_profile():
    """
    Regenerate a profile with all current devices.
    
    Request body:
        {
            "bundle_id": "*" or specific bundle ID,
            "name": "Profile Name" (optional)
        }
    """
    data       = request.get_json(silent=True) or {}
    bundle_id  = (data.get("bundle_id") or "").strip()
    profile_name = data.get("name") or f"AdHoc {bundle_id} {datetime.utcnow().strftime('%Y%m%d_%H%M')}"

    if not bundle_id:
        return jsonify({"error": "bundle_id is required"}), 400

    from datetime import datetime as _dt
    timestamp = _dt.utcnow().strftime('%Y%m%d%H%M%S')
    output_path = str(
        Config.PROFILE_CACHE_DIR / f"Cook-IPA-Auto_{timestamp}.mobileprovision"
    )
    Config.PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        api  = _client()
        logs = []
        
        # Fetch all devices (including DISABLED)
        all_devices = api.list_devices(platform="IOS", status=None)
        enabled_count = sum(1 for d in all_devices if d.get("attributes", {}).get("status") == "ENABLED")
        log.info(f"Regenerating profile with {len(all_devices)} devices ({enabled_count} enabled)")
        
        result = api.create_and_save_adhoc_profile(
            bundle_identifier=bundle_id,
            profile_name=profile_name,
            output_path=output_path,
            log_callback=lambda msg: logs.append(msg),
        )
        
        return jsonify({
            "success": True,
            "profile": result,
            "device_count_total": len(all_devices),
            "device_count_enabled": enabled_count,
            "device_count_in_profile": result.get("device_count_actual", 0),
            "logs": logs,
            "message": f"Profile regenerated: {result.get('device_count_actual', 0)} enabled devices included (out of {len(all_devices)} total)",
        }), 201
    except AppStoreConnectError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        log.exception("Profile regeneration failed")
        return jsonify({"error": str(e)}), 500


@profiles_bp.route("/profiles/check-update", methods=["POST"])
def check_and_update_profile():
    """
    Check if active profile needs regeneration and optionally regenerate.
    
    Request body:
        {
            "auto_regenerate": true/false (default: false)
        }
    
    Returns:
        {
            "needs_update": bool,
            "active_profile": {...},
            "missing_enabled_devices": [...],
            "regenerated": bool (if auto_regenerate=true)
        }
    """
    from app.services.mobileprovision_parser import (
        parse_mobileprovision,
        check_missing_devices,
    )
    
    data = request.get_json(silent=True) or {}
    auto_regenerate = data.get("auto_regenerate", False)
    
    active_path = Config.get_mobileprovision_path()
    if not active_path or not Path(active_path).exists():
        return jsonify({"error": "No active profile found"}), 404
    
    try:
        # Parse active profile
        metadata = parse_mobileprovision(active_path)
        if not metadata:
            return jsonify({"error": "Failed to parse active profile"}), 500
        
        # Fetch Apple API devices
        api = _client()
        api_devices = api.list_devices(platform="IOS", status=None)
        
        # Check missing devices
        missing = check_missing_devices(metadata, api_devices)
        enabled_missing = [d for d in missing if d.get("attributes", {}).get("status") == "ENABLED"]
        
        needs_update = len(enabled_missing) > 0
        
        result = {
            "needs_update": needs_update,
            "active_profile": {
                "path": active_path,
                "name": metadata["name"],
                "bundle_id": metadata["bundle_id"],
                "device_count": len(metadata["devices"]),
                "expiration_date": metadata["expiration_date"].isoformat() if metadata["expiration_date"] else None,
            },
            "missing_enabled_devices": [
                {
                    "id": d["id"],
                    "name": d["attributes"]["name"],
                    "udid": d["attributes"]["udid"],
                }
                for d in enabled_missing
            ],
            "total_devices": len(api_devices),
            "enabled_devices": sum(1 for d in api_devices if d.get("attributes", {}).get("status") == "ENABLED"),
        }
        
        # Auto-regenerate if requested and needed
        if auto_regenerate and needs_update:
            log.info(f"Auto-regenerating profile for {metadata['bundle_id']} — {len(enabled_missing)} new enabled devices found")
            
            from datetime import datetime as _dt
            timestamp = _dt.utcnow().strftime('%Y%m%d%H%M%S')
            output_path = str(
                Config.PROFILE_CACHE_DIR / f"Cook-IPA-Auto_{timestamp}.mobileprovision"
            )
            Config.PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            
            logs = []
            regen_result = api.create_and_save_adhoc_profile(
                bundle_identifier=metadata["bundle_id"],
                profile_name=f"{metadata['name']} (Auto-Updated)",
                output_path=output_path,
                log_callback=lambda msg: logs.append(msg),
            )
            
            result["regenerated"] = True
            result["new_profile"] = regen_result
            result["logs"] = logs
        else:
            result["regenerated"] = False
        
        return jsonify(result)
        
    except AppStoreConnectError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        log.exception("Profile check failed")
        return jsonify({"error": str(e)}), 500


