"""
.mobileprovision file parser — extracts metadata including device UUIDs.
"""
import logging
import plistlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


def parse_mobileprovision(path: str) -> Optional[Dict[str, Any]]:
    """
    Parse a .mobileprovision file and extract metadata.
    
    Returns:
        {
            "name": str,
            "team_name": str,
            "app_id_name": str,
            "bundle_id": str,
            "profile_type": str (e.g., "Development", "Ad Hoc", "Distribution"),
            "uuid": str,
            "expiration_date": datetime,
            "creation_date": datetime,
            "platform": list[str],
            "devices": list[str] (UUIDs),
            "certificates": list[dict],
        }
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        
        # .mobileprovision is XML plist wrapped in CMS signature
        # Extract XML between <?xml and </plist>
        match = re.search(rb"<\?xml.*</plist>", data, re.DOTALL)  # Fixed: use raw bytes string
        if not match:
            log.error(f"Cannot find plist in {path}")
            return None
        
        plist_data = match.group(0)
        plist = plistlib.loads(plist_data)
        
        # Extract fields
        profile_type = _determine_profile_type(plist)
        
        # Extract bundle ID correctly (remove team ID prefix, keep rest)
        app_id = plist.get("Entitlements", {}).get("application-identifier", "Unknown")
        bundle_id = app_id.split(".", 1)[-1] if "." in app_id else app_id  # Fixed: split on first dot only
        
        return {
            "name": plist.get("Name", "Unknown"),
            "team_name": plist.get("TeamName", "Unknown"),
            "app_id_name": plist.get("AppIDName", "Unknown"),
            "bundle_id": bundle_id,
            "profile_type": profile_type,
            "uuid": plist.get("UUID", "Unknown"),
            "expiration_date": plist.get("ExpirationDate"),
            "creation_date": plist.get("CreationDate"),
            "platform": plist.get("Platform", []),
            "devices": plist.get("ProvisionedDevices", []),  # Only exists in Dev/Ad Hoc
            "certificates": [
                {
                    "subject": _get_cert_subject(cert),
                    "serial": _get_cert_serial(cert),
                }
                for cert in plist.get("DeveloperCertificates", [])
            ],
        }
    except Exception as e:
        log.exception(f"Failed to parse {path}")
        return None


def _determine_profile_type(plist: dict) -> str:
    """
    Determine profile type from entitlements and provisioned devices.
    - Development: has get-task-allow=true, has devices
    - Ad Hoc: no get-task-allow, has devices
    - App Store: no devices, has ProvisionsAllDevices or beta-reports-active
    - Enterprise: has ProvisionsAllDevices
    """
    entitlements = plist.get("Entitlements", {})
    has_devices = bool(plist.get("ProvisionedDevices"))
    get_task_allow = entitlements.get("get-task-allow", False)
    provisions_all = plist.get("ProvisionsAllDevices", False)
    
    if provisions_all:
        return "Enterprise"
    if has_devices:
        return "Development" if get_task_allow else "Ad Hoc"
    return "App Store"


def _get_cert_subject(cert_data: bytes) -> str:
    """Extract CN from certificate DER data."""
    try:
        from cryptography.x509 import load_der_x509_certificate
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.backends import default_backend
        cert = load_der_x509_certificate(cert_data, default_backend())
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return attrs[0].value if attrs else "Unknown"
    except Exception as e:
        log.debug(f"Failed to extract cert subject: {e}")
        return "Unknown"


def _get_cert_serial(cert_data: bytes) -> str:
    """Extract serial number from certificate."""
    try:
        from cryptography.x509 import load_der_x509_certificate
        from cryptography.hazmat.backends import default_backend
        cert = load_der_x509_certificate(cert_data, default_backend())
        return f"{cert.serial_number:X}"
    except Exception as e:  # Fixed: catch Exception, not all
        log.debug(f"Failed to extract cert serial: {e}")
        return "Unknown"


def match_profile_to_apple_api(
    local_profile: Dict[str, Any],
    api_profiles: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Match a local .mobileprovision to an Apple API profile by UUID, falling back to name.
    
    Args:
        local_profile: Parsed local profile from parse_mobileprovision()
        api_profiles: List of profiles from AppStoreConnectClient.list_profiles()
    
    Returns:
        Matching API profile dict, or None if not found
    """
    local_uuid = local_profile.get("uuid")
    local_name = local_profile.get("name")

    for api_profile in api_profiles:
        attrs = api_profile.get("attributes", {})
        if local_uuid and attrs.get("uuid") == local_uuid:
            return api_profile

    # Fall back to name matching if UUID is unavailable
    if local_name:
        for api_profile in api_profiles:
            if api_profile["attributes"]["name"] == local_name:
                return api_profile

    return None


def check_missing_devices(
    local_profile: Dict[str, Any],
    all_devices: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Check which devices in Apple API are NOT in the local profile.
    
    Args:
        local_profile: Parsed profile from parse_mobileprovision()
        all_devices: List of devices from AppStoreConnectClient.list_devices()
    
    Returns:
        List of devices not covered by this profile
    """
    profile_uuids = set(local_profile.get("devices", []))
    missing = []
    
    for device in all_devices:
        device_udid = device["attributes"]["udid"]
        if device_udid not in profile_uuids:
            missing.append(device)
    
    return missing
