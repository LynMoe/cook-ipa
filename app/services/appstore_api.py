"""
App Store Connect API Client - Ad Hoc Distribution

Handles:
  - JWT authentication (auto-refresh)
  - Device registration (POST /v1/devices)
  - Device listing (GET /v1/devices)
  - Bundle ID lookup (GET /v1/bundleIds)
  - Certificate lookup (GET /v1/certificates)
  - Ad Hoc Profile creation (POST /v1/profiles)
  - Profile listing (GET /v1/profiles)
  - Profile download (base64 → .mobileprovision)

Apple API docs: https://developer.apple.com/documentation/appstoreconnectapi
"""

import time
import logging
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable

import jwt
import requests

log = logging.getLogger(__name__)

ASC_BASE = "https://api.appstoreconnect.apple.com/v1"
JWT_LIFETIME = 18 * 60  # seconds (Apple max 20 min)


class AppStoreConnectError(Exception):
    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AppStoreConnectClient:
    """App Store Connect API client with automatic JWT refresh."""

    def __init__(self, key_id: str, issuer_id: str, private_key_path: str):
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.private_key_path = Path(private_key_path)
        self._private_key: Optional[str] = None
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    def _load_private_key(self) -> str:
        if self._private_key is None:
            if not self.private_key_path.exists():
                raise AppStoreConnectError(
                    f"Apple .p8 private key not found: {self.private_key_path}"
                )
            self._private_key = self.private_key_path.read_text().strip()
        return self._private_key

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        private_key = self._load_private_key()
        expires_at = int(now) + JWT_LIFETIME
        payload = {
            "iss": self.issuer_id,
            "iat": int(now),
            "exp": expires_at,
            "aud": "appstoreconnect-v1",
        }
        self._token = jwt.encode(
            payload, private_key, algorithm="ES256",
            headers={"kid": self.key_id},
        )
        self._token_expires_at = expires_at
        log.debug("JWT refreshed, expires %s", datetime.fromtimestamp(expires_at))
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json_body: dict = None,
        timeout: int = 30,
    ) -> dict:
        url = f"{ASC_BASE}{path}" if path.startswith("/") else path
        resp = requests.request(
            method, url, headers=self._headers(),
            params=params, json=json_body, timeout=timeout,
        )
        if not resp.ok:
            raise AppStoreConnectError(
                f"API {method} {path} [{resp.status_code}]: {resp.text[:400]}",
                status_code=resp.status_code,
                body=resp.text,
            )
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------ #
    # Devices
    # ------------------------------------------------------------------ #

    def list_devices(self, platform: str = "IOS", limit: int = 200, status: Optional[str] = None) -> list:
        """
        GET /v1/devices - List all registered devices.
        
        Args:
            platform: IOS, MAC_OS, etc.
            limit: Max results (default 200)
            status: ENABLED, DISABLED, or None for all (default: None)
        """
        params = {"filter[platform]": platform, "limit": limit}
        if status:
            params["filter[status]"] = status
        data = self._request("GET", "/devices", params=params)
        return data.get("data", [])

    def register_device(self, name: str, udid: str, platform: str = "IOS") -> dict:
        """
        POST /v1/devices - Register a new device.

        Returns the created device resource dict.
        """
        body = {
            "data": {
                "type": "devices",
                "attributes": {
                    "name": name,
                    "udid": udid,
                    "platform": platform,
                },
            }
        }
        data = self._request("POST", "/devices", json_body=body)
        return data.get("data", {})

    # ------------------------------------------------------------------ #
    # Bundle IDs
    # ------------------------------------------------------------------ #

    def list_bundle_ids(self, identifier: Optional[str] = None) -> list:
        """GET /v1/bundleIds - List bundle IDs registered in Apple Developer."""
        params = {"limit": 100}
        if identifier:
            params["filter[identifier]"] = identifier
        data = self._request("GET", "/bundleIds", params=params)
        return data.get("data", [])

    def get_bundle_id_resource(self, identifier: str) -> Optional[dict]:
        """Return the BundleId resource for a given bundle identifier string.
        
        For wildcard '*', fetches all bundle IDs and matches exactly.
        """
        if identifier == "*":
            # Wildcard '*' may not work in URL filter; fetch all and match
            items = self.list_bundle_ids()
            for item in items:
                if item["attributes"]["identifier"] == "*":
                    return item
            return None
        items = self.list_bundle_ids(identifier=identifier)
        return items[0] if items else None

    # ------------------------------------------------------------------ #
    # Certificates
    # ------------------------------------------------------------------ #

    def list_certificates(
        self,
        cert_type: Optional[str] = None,
    ) -> list:
        """
        GET /v1/certificates
        cert_type: IOS_DISTRIBUTION, IOS_DEVELOPMENT, DISTRIBUTION, etc.
        """
        params = {"limit": 100}
        if cert_type:
            params["filter[certificateType]"] = cert_type
        data = self._request("GET", "/certificates", params=params)
        return data.get("data", [])

    def get_distribution_cert(self) -> Optional[dict]:
        """Return the first active IOS_DISTRIBUTION certificate."""
        # Try IOS_DISTRIBUTION first, then DISTRIBUTION
        for ct in ("IOS_DISTRIBUTION", "DISTRIBUTION"):
            certs = self.list_certificates(cert_type=ct)
            if certs:
                return certs[0]
        return None

    # ------------------------------------------------------------------ #
    # Profiles
    # ------------------------------------------------------------------ #

    def list_profiles(self, profile_type: Optional[str] = None) -> list:
        """GET /v1/profiles - List provisioning profiles."""
        params = {"limit": 100}
        if profile_type:
            params["filter[profileType]"] = profile_type
        data = self._request("GET", "/profiles", params=params)
        return data.get("data", [])

    def get_profile(self, profile_id: str) -> Optional[dict]:
        """GET /v1/profiles/{id} - Fetch a single profile resource."""
        data = self._request("GET", f"/profiles/{profile_id}")
        return data.get("data")

    def create_adhoc_profile(
        self,
        name: str,
        bundle_id_resource_id: str,
        certificate_ids: List[str],
        device_ids: List[str],
    ) -> dict:
        """
        POST /v1/profiles - Create a new Ad Hoc provisioning profile.

        Args:
            name: Profile display name
            bundle_id_resource_id: The resource ID of the BundleId (not the string)
            certificate_ids: List of Certificate resource IDs
            device_ids: List of Device resource IDs

        Returns:
            The created profile resource dict. Attributes include base64 'profileContent'.
        """
        body = {
            "data": {
                "type": "profiles",
                "attributes": {
                    "name": name,
                    "profileType": "IOS_APP_ADHOC",
                },
                "relationships": {
                    "bundleId": {
                        "data": {"id": bundle_id_resource_id, "type": "bundleIds"}
                    },
                    "certificates": {
                        "data": [{"id": cid, "type": "certificates"} for cid in certificate_ids]
                    },
                    "devices": {
                        "data": [{"id": did, "type": "devices"} for did in device_ids]
                    },
                },
            }
        }
        data = self._request("POST", "/profiles", json_body=body)
        return data.get("data", {})

    def download_profile_content(self, profile_resource: dict) -> bytes:
        """
        Decode the base64 profileContent from a profile resource.
        Returns the raw .mobileprovision bytes.
        """
        content_b64 = profile_resource.get("attributes", {}).get("profileContent", "")
        if not content_b64:
            raise AppStoreConnectError("Profile resource has no profileContent")
        return base64.b64decode(content_b64)

    def delete_profile(self, profile_id: str) -> None:
        """DELETE /v1/profiles/{id}"""
        self._request("DELETE", f"/profiles/{profile_id}")

    def create_and_save_adhoc_profile(
        self,
        bundle_identifier: str,
        profile_name: str,
        output_path: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """
        High-level helper: looks up bundle ID + dist cert + all devices,
        creates a new Ad Hoc profile, saves the .mobileprovision to output_path.

        Returns a summary dict with Apple resource IDs.
        """

        def _log(msg):
            if log_callback:
                log_callback(msg)
            log.info(msg)

        # 1. Look up BundleId resource
        _log(f"Looking up bundle ID: {bundle_identifier}")
        bundle_resource = self.get_bundle_id_resource(bundle_identifier)
        if not bundle_resource:
            raise AppStoreConnectError(
                f"Bundle ID '{bundle_identifier}' not found in Apple Developer. "
                "Please register it first at developer.apple.com."
            )
        bundle_resource_id = bundle_resource["id"]
        _log(f"Found bundle ID resource: {bundle_resource_id}")

        # 2. Look up Distribution certificate
        _log("Looking up Distribution certificate...")
        cert = self.get_distribution_cert()
        if not cert:
            raise AppStoreConnectError(
                "No Distribution certificate found. "
                "Please create an iOS Distribution certificate in Apple Developer."
            )
        cert_id = cert["id"]
        cert_name = cert.get("attributes", {}).get("name", cert_id)
        _log(f"Using certificate: {cert_name} ({cert_id})")

        # 3. Get all registered devices (including DISABLED)
        # Note: Apple API will automatically exclude DISABLED devices when creating the profile
        _log("Fetching all registered devices...")
        devices = self.list_devices(status=None)  # None = all statuses
        device_ids = [d["id"] for d in devices]
        enabled_count = sum(1 for d in devices if d.get("attributes", {}).get("status") == "ENABLED")
        _log(f"Found {len(devices)} total devices ({enabled_count} enabled, {len(devices) - enabled_count} disabled)")
        _log("Note: Apple will only include ENABLED devices in the profile")

        if not device_ids:
            raise AppStoreConnectError(
                "No enabled devices found. Register at least one device first."
            )

        # 4. Create the profile
        _log(f"Creating Ad Hoc profile: '{profile_name}'...")
        profile = self.create_adhoc_profile(
            name=profile_name,
            bundle_id_resource_id=bundle_resource_id,
            certificate_ids=[cert_id],
            device_ids=device_ids,
        )
        profile_id = profile["id"]
        expiry = profile.get("attributes", {}).get("expirationDate", "unknown")
        _log(f"Profile created: {profile_id} (expires: {expiry})")

        # 5. Save .mobileprovision
        mp_bytes = self.download_profile_content(profile)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(mp_bytes)
        _log(f"Saved profile to: {output_path} ({len(mp_bytes)} bytes)")

        return {
            "apple_profile_id": profile_id,
            "name": profile_name,
            "bundle_id": bundle_identifier,
            "expiry_date": expiry,
            "device_count_requested": len(device_ids),
            "device_count_actual": len([d for d in devices if d.get("attributes", {}).get("status") == "ENABLED"]),
            "profile_path": output_path,
        }

