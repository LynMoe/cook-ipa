"""
ProfileResolver — resolve or create an Ad Hoc profile that covers all ENABLED device UDIDs.

Algorithm:
  1. Fetch Ad Hoc profiles from Apple API; pick the one created by Cook-IPA-Auto with latest expiration.
  2. Ensure that profile is available locally (download to cache if needed); parse device UDIDs.
  3. Fetch current ENABLED devices from Apple.
  4. If enabled_devices ⊆ profile_devices, return path to that profile.
  5. Otherwise create a new Ad Hoc profile including all ENABLED devices, save to cache, return path.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from config import Config
from app.services.appstore_api import AppStoreConnectClient, AppStoreConnectError
from app.services.mobileprovision_parser import parse_mobileprovision

log = logging.getLogger(__name__)

# Name prefix for auto-created profiles (Apple API and local filenames)
COOK_AUTO_PROFILE_PREFIX = "Cook IPA Auto"
COOK_AUTO_FILE_PREFIX = "Cook-IPA-Auto"


def _is_cook_auto_profile(name: str) -> bool:
    """True if profile is created by this app (Cook IPA Auto)."""
    if not name:
        return False
    n = name.strip()
    return n.startswith(COOK_AUTO_PROFILE_PREFIX) or n.startswith("Cook-IPA-Auto")


def _parse_apple_expiration(expiration_date: Optional[str]) -> datetime:
    """Parse Apple API expiration date string to datetime for sorting."""
    if not expiration_date:
        return datetime.min
    try:
        # ISO format e.g. 2025-12-31T00:00:00.000Z
        return datetime.fromisoformat(expiration_date.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


class ProfileResolver:
    """Resolves the provisioning profile path to use for signing (reuse or create)."""

    def __init__(
        self,
        key_id: str = None,
        issuer_id: str = None,
        private_key_path: str = None,
        profile_cache_dir: Path = None,
    ):
        self.key_id = key_id or Config.APPLE_KEY_ID
        self.issuer_id = issuer_id or Config.APPLE_ISSUER_ID
        self.private_key_path = private_key_path or Config.APPLE_PRIVATE_KEY_PATH
        self.profile_cache_dir = Path(profile_cache_dir or Config.PROFILE_CACHE_DIR)

    def _client(self) -> AppStoreConnectClient:
        return AppStoreConnectClient(
            key_id=self.key_id,
            issuer_id=self.issuer_id,
            private_key_path=self.private_key_path,
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Read-only status: latest Cook-IPA-Auto profile, coverage of enabled devices, missing list.
        Does not create a profile; may download from Apple to compute coverage.
        """
        out = {
            "active_path": None,
            "latest": None,
            "coverage": False,
            "missing_devices": [],
            "enabled_count": 0,
            "error": None,
        }
        try:
            api = self._client()
            self.profile_cache_dir.mkdir(parents=True, exist_ok=True)
            all_devices = api.list_devices(platform="IOS", status=None)
            enabled = [d for d in all_devices if d.get("attributes", {}).get("status") == "ENABLED"]
            enabled_udids = {d["attributes"]["udid"] for d in enabled}
            out["enabled_count"] = len(enabled)

            profiles = api.list_profiles(profile_type="IOS_APP_ADHOC")
            cook_auto = [p for p in profiles if _is_cook_auto_profile(p.get("attributes", {}).get("name", ""))]
            if not cook_auto:
                out["missing_devices"] = [
                    {"udid": d["attributes"]["udid"], "name": d["attributes"].get("name", ""), "platform": d["attributes"].get("platform", "IOS")}
                    for d in enabled
                ]
                out["coverage"] = False
                # active_path = latest file in cache by mtime if any
                cached = sorted(
                    self.profile_cache_dir.glob("*.mobileprovision"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if cached:
                    out["active_path"] = str(cached[0])
                return out

            cook_auto.sort(
                key=lambda p: _parse_apple_expiration(p.get("attributes", {}).get("expirationDate")),
                reverse=True,
            )
            latest_apple = cook_auto[0]
            attrs = latest_apple.get("attributes", {})
            profile_uuid = attrs.get("uuid")
            out["latest"] = {
                "id": latest_apple["id"],
                "name": attrs.get("name", ""),
                "uuid": profile_uuid,
                "expiration_date": attrs.get("expirationDate"),
            }

            local_path = self._ensure_profile_local(api, latest_apple, profile_uuid, lambda msg, level="info": None)
            if not local_path:
                out["missing_devices"] = [
                    {"udid": d["attributes"]["udid"], "name": d["attributes"].get("name", ""), "platform": d["attributes"].get("platform", "IOS")}
                    for d in enabled
                ]
                out["coverage"] = False
                return out

            meta = parse_mobileprovision(local_path)
            if not meta:
                out["missing_devices"] = [
                    {"udid": d["attributes"]["udid"], "name": d["attributes"].get("name", ""), "platform": d["attributes"].get("platform", "IOS")}
                    for d in enabled
                ]
                out["coverage"] = False
                return out

            profile_devices = set(meta.get("devices", []))
            out["latest"]["device_count"] = len(profile_devices)
            out["active_path"] = local_path
            out["coverage"] = enabled_udids.issubset(profile_devices)
            missing_udids = enabled_udids - profile_devices
            out["missing_devices"] = [
                {"udid": d["attributes"]["udid"], "name": d["attributes"].get("name", ""), "platform": d["attributes"].get("platform", "IOS")}
                for d in enabled
                if d["attributes"]["udid"] in missing_udids
            ]
            return out
        except AppStoreConnectError as e:
            out["error"] = str(e)
            return out
        except Exception as e:
            log.exception("ProfileResolver.get_status failed")
            out["error"] = str(e)
            return out

    def resolve(self, log_callback: Optional[Callable[[str, str], None]] = None) -> Optional[str]:
        """
        Return path to a .mobileprovision that covers all current ENABLED devices.
        Reuses latest Cook-IPA-Auto profile if it covers them; otherwise creates a new one.

        log_callback(msg, level) with level in ("info", "error", "success").
        """
        def _log(msg: str, level: str = "info"):
            if log_callback:
                log_callback(msg, level)
            if level == "error":
                log.error(msg)
            else:
                log.info(msg)

        try:
            api = self._client()
            self.profile_cache_dir.mkdir(parents=True, exist_ok=True)

            # 1. Fetch ENABLED devices
            _log("Fetching enabled devices from Apple...")
            all_devices = api.list_devices(platform="IOS", status=None)
            enabled = [d for d in all_devices if d.get("attributes", {}).get("status") == "ENABLED"]
            enabled_udids = {d["attributes"]["udid"] for d in enabled}

            if not enabled_udids:
                _log("No enabled devices found. Register at least one device first.", "error")
                return None

            _log(f"Found {len(enabled_udids)} enabled device(s)")

            # 2. Fetch Ad Hoc profiles from Apple; pick Cook-IPA-Auto with latest expiration
            _log("Fetching Ad Hoc profiles from Apple...")
            profiles = api.list_profiles(profile_type="IOS_APP_ADHOC")
            cook_auto = [p for p in profiles if _is_cook_auto_profile(p.get("attributes", {}).get("name", ""))]
            if not cook_auto:
                _log("No Cook-IPA-Auto profile found. Creating new profile...")
                return self._create_and_save(api, _log)

            # Sort by expiration date descending (latest first)
            cook_auto.sort(
                key=lambda p: _parse_apple_expiration(p.get("attributes", {}).get("expirationDate")),
                reverse=True,
            )
            latest_apple = cook_auto[0]
            profile_uuid = latest_apple.get("attributes", {}).get("uuid")
            profile_id = latest_apple["id"]
            profile_name = latest_apple.get("attributes", {}).get("name", "")

            # 3. Ensure profile is on disk (local cache or download)
            local_path = self._ensure_profile_local(api, latest_apple, profile_uuid, _log)
            if not local_path:
                _log("Failed to get profile file. Creating new profile...", "error")
                return self._create_and_save(api, _log)

            # 4. Parse profile device UDIDs
            meta = parse_mobileprovision(local_path)
            if not meta:
                _log("Failed to parse profile. Creating new profile...", "error")
                return self._create_and_save(api, _log)

            profile_devices = set(meta.get("devices", []))

            # 5. Check coverage: enabled_udids ⊆ profile_devices
            if enabled_udids.issubset(profile_devices):
                _log(f"Using existing profile: {profile_name} (UUID: {profile_uuid})")
                _log(f"Profile path: {local_path}")
                return local_path

            missing = enabled_udids - profile_devices
            _log(f"Profile missing {len(missing)} enabled device(s). Creating new profile...")
            return self._create_and_save(api, _log)

        except AppStoreConnectError as e:
            _log(f"Apple API error: {e}", "error")
            return None
        except Exception as e:
            _log(f"Unexpected error: {e}", "error")
            log.exception("ProfileResolver failed")
            return None

    def _ensure_profile_local(
        self,
        api: AppStoreConnectClient,
        profile_resource: dict,
        profile_uuid: Optional[str],
        log_callback,
    ) -> Optional[str]:
        """Return path to .mobileprovision in cache; download from Apple if not present."""
        cache_dir = self.profile_cache_dir
        # Check existing cache by UUID
        for p in cache_dir.glob("*.mobileprovision"):
            meta = parse_mobileprovision(str(p))
            if meta and meta.get("uuid") == profile_uuid:
                log_callback(f"Using cached profile: {p}")
                return str(p)

        # Download and save
        log_callback("Downloading profile from Apple...")
        try:
            mp_bytes = api.download_profile_content(profile_resource)
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            out_path = cache_dir / f"{COOK_AUTO_FILE_PREFIX}_{timestamp}.mobileprovision"
            out_path.write_bytes(mp_bytes)
            log_callback(f"Saved profile to {out_path}")
            return str(out_path)
        except Exception as e:
            log_callback(f"Download failed: {e}", "error")
            return None

    def _create_and_save(
        self,
        api: AppStoreConnectClient,
        log_callback,
    ) -> Optional[str]:
        """Create new Ad Hoc profile with all ENABLED devices and save to cache."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        output_path = str(self.profile_cache_dir / f"{COOK_AUTO_FILE_PREFIX}_{timestamp}.mobileprovision")
        profile_name = f"{COOK_AUTO_PROFILE_PREFIX} {timestamp}"

        def _log(msg: str):
            log_callback(msg)

        result = api.create_and_save_adhoc_profile(
            bundle_identifier="*",
            profile_name=profile_name,
            output_path=output_path,
            log_callback=_log,
        )
        log_callback(f"Profile created: {result.get('name')} ({result.get('device_count_actual', 0)} devices)", "success")
        return output_path
