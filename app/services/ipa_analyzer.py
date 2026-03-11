"""
IPA Analyzer - Extracts metadata from .ipa files without modifying them.
Reads Info.plist, extracts bundle ID, version, app name, and icon.
"""

import zipfile
import plistlib
import io
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class IPAAnalysisResult:
    def __init__(self):
        self.bundle_id: str = ""
        self.bundle_version: str = ""          # CFBundleVersion  (build number, e.g. "42")
        self.short_version: str = ""           # CFBundleShortVersionString (e.g. "1.2.3")
        self.app_name: str = ""                # CFBundleDisplayName / CFBundleName
        self.minimum_os_version: str = ""
        self.icon_data: Optional[bytes] = None # PNG bytes of the app icon
        self.executable_name: str = ""
        self.app_dir_name: str = ""            # e.g. "MyApp.app"

    def to_dict(self):
        return {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "short_version": self.short_version,
            "app_name": self.app_name,
            "minimum_os_version": self.minimum_os_version,
            "executable_name": self.executable_name,
        }


def analyze_ipa(ipa_path: str) -> IPAAnalysisResult:
    """Extract metadata from an IPA file."""
    result = IPAAnalysisResult()
    ipa_path = Path(ipa_path)

    if not ipa_path.exists():
        raise FileNotFoundError(f"IPA not found: {ipa_path}")

    with zipfile.ZipFile(str(ipa_path), "r") as zf:
        # Find Payload/*.app/Info.plist
        info_plist_path = _find_info_plist(zf)
        if not info_plist_path:
            raise ValueError("Could not find Info.plist inside IPA")

        # Parse app dir name from path
        parts = info_plist_path.split("/")
        if len(parts) >= 2:
            result.app_dir_name = parts[1]  # e.g. "MyApp.app"

        with zf.open(info_plist_path) as f:
            plist_data = plistlib.load(f)

        result.bundle_id = plist_data.get("CFBundleIdentifier", "")
        result.bundle_version = plist_data.get("CFBundleVersion", "")
        result.short_version = plist_data.get("CFBundleShortVersionString", "")
        result.minimum_os_version = plist_data.get("MinimumOSVersion", "")
        result.executable_name = plist_data.get("CFBundleExecutable", "")

        # Prefer display name, fall back to bundle name
        result.app_name = (
            plist_data.get("CFBundleDisplayName")
            or plist_data.get("CFBundleName")
            or result.executable_name
            or "Unknown"
        )

        # Try to extract icon
        result.icon_data = _extract_icon(zf, info_plist_path, plist_data)

    log.info(
        "IPA analysis: %s  v%s (%s)  bundle=%s",
        result.app_name, result.short_version, result.bundle_version, result.bundle_id,
    )
    return result


def _find_info_plist(zf: zipfile.ZipFile) -> Optional[str]:
    """Locate Payload/<AppName>.app/Info.plist in the zip."""
    for name in zf.namelist():
        parts = name.split("/")
        # Expect: Payload / <App>.app / Info.plist
        if (
            len(parts) == 3
            and parts[0] == "Payload"
            and parts[1].endswith(".app")
            and parts[2] == "Info.plist"
        ):
            return name
    return None


def _extract_icon(
    zf: zipfile.ZipFile,
    info_plist_path: str,
    plist_data: dict,
) -> Optional[bytes]:
    """Try to extract the best quality app icon from the IPA."""
    app_prefix = "/".join(info_plist_path.split("/")[:2]) + "/"

    # Collect candidate icon filenames from plist
    candidates = []
    icon_dict = plist_data.get("CFBundleIcons", {})
    primary = icon_dict.get("CFBundlePrimaryIcon", {})
    icon_files = primary.get("CFBundleIconFiles", [])
    for icon_file in icon_files:
        candidates.append(icon_file)

    # Also try legacy key
    for ic in plist_data.get("CFBundleIconFiles", []):
        candidates.append(ic)

    # Prefer larger icons (180x180 or 120x120 typical for iPhone)
    all_names = zf.namelist()
    for candidate in candidates:
        for name in all_names:
            if name.startswith(app_prefix) and candidate in name and name.endswith(".png"):
                try:
                    with zf.open(name) as f:
                        return f.read()
                except Exception:
                    pass

    # Fallback: any AppIcon*.png
    for name in all_names:
        if name.startswith(app_prefix) and "AppIcon" in name and name.endswith(".png"):
            try:
                with zf.open(name) as f:
                    return f.read()
            except Exception:
                pass

    return None
