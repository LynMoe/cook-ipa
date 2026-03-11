"""
Build Pipeline - Ad Hoc OTA distribution workflow:
  1. Analyze IPA (extract metadata, icon)
  2. Resolve profile (reuse latest Cook-IPA-Auto if it covers all ENABLED devices, else create new)
  3. Re-sign IPA with zsign using the resolved profile
  4. Generate OTA manifest.plist for iOS installation

Runs in a background thread. State stored as JSON files.
"""

import threading
import plistlib
import logging
from pathlib import Path

from config import Config
from app.services.build_store import get_store, STATUS_ANALYZING, STATUS_SIGNING, STATUS_DONE, STATUS_FAILED
from app.domain.profile_resolver import ProfileResolver

log = logging.getLogger(__name__)


def start_pipeline(app, build_uuid: str):
    """Launch the pipeline in a daemon background thread."""
    thread = threading.Thread(
        target=_run_pipeline,
        args=(app, build_uuid),
        daemon=True,
        name=f"pipeline-{build_uuid[:8]}",
    )
    thread.start()
    return thread


def _run_pipeline(app, build_uuid: str):
    """Main pipeline — runs in background thread."""
    with app.app_context():
        store = get_store()
        build = store.get(build_uuid)
        if not build:
            return

        def _log(msg: str, level: str = "info"):
            store.append_log(build_uuid, msg, level)

        def _fail(msg: str):
            store.update(build_uuid, status=STATUS_FAILED, error_message=msg)
            _log(f"FAILED: {msg}", "error")

        def _status(status: str, msg: str = ""):
            store.update(build_uuid, status=status)
            if msg:
                _log(msg)

        try:
            # ── Step 1: Analyze ──────────────────────────────────────────────
            _status(STATUS_ANALYZING, "Analyzing IPA...")
            from app.services.ipa_analyzer import analyze_ipa

            result = analyze_ipa(build["original_ipa_path"])
            store.update(
                build_uuid,
                bundle_id=result.bundle_id,
                bundle_version=result.bundle_version,
                short_version=result.short_version,
                app_name=result.app_name,
            )
            _log(
                f"App: {result.app_name} | {result.bundle_id} | "
                f"v{result.short_version} ({result.bundle_version})"
            )

            if not result.bundle_id:
                return _fail("Could not extract Bundle ID from IPA")

            # Save icon
            build_dir = store.build_dir(build_uuid)
            if result.icon_data:
                icon_path = build_dir / "icon.png"
                icon_path.write_bytes(result.icon_data)
                store.update(build_uuid, icon_path=str(icon_path))

            # ── Step 2: Resolve profile then Sign ─────────────────────────────
            _status(STATUS_SIGNING, "Resolving Ad Hoc profile...")
            resolver = ProfileResolver()
            mp = resolver.resolve(log_callback=lambda msg, level="info": _log(msg, level))
            if not mp or not Path(mp).exists():
                return _fail("Failed to resolve profile (no enabled devices or Apple API error).")

            _status(STATUS_SIGNING, "Re-signing IPA with Ad Hoc profile...")
            p12    = Config.P12_PATH
            p12_pw = Config.P12_PASSWORD

            if not Path(p12).exists():
                return _fail(f".p12 certificate not found: {p12}")
            if not Path(mp).exists():
                return _fail(f".mobileprovision not found: {mp}")

            from app.services.ipa_signer import sign_ipa, SigningError

            signed_path = str(build_dir / "signed.ipa")
            try:
                sign_ipa(
                    input_ipa=build["original_ipa_path"],
                    output_ipa=signed_path,
                    p12_path=p12,
                    p12_password=p12_pw,
                    mobileprovision_path=mp,
                    zsign_path=Config.ZSIGN_PATH,
                    log_callback=_log,
                )
            except SigningError as e:
                return _fail(f"Signing failed: {e}")

            store.update(build_uuid, signed_ipa_path=signed_path)
            _log("IPA signed successfully", "success")

            # ── Step 3: Upload to S3 and generate OTA manifest ─────────────
            from app.services import s3_storage

            build = store.get(build_uuid)
            try:
                _log("Uploading signed IPA to S3...")
                ipa_key = s3_storage.object_key(build_uuid, "signed.ipa")
                s3_ipa_url = s3_storage.upload_file(
                    signed_path, ipa_key, "application/octet-stream"
                )
                _log(f"Uploaded IPA: {ipa_key}", "success")

                manifest_plist = _make_manifest(
                    ipa_url=s3_ipa_url,
                    bundle_id=build["bundle_id"],
                    bundle_version=build["bundle_version"],
                    short_version=build["short_version"],
                    app_name=build["app_name"],
                )
                manifest_bytes = plistlib.dumps(manifest_plist, fmt=plistlib.FMT_XML)
                manifest_key = s3_storage.object_key(build_uuid, "manifest.plist")
                s3_manifest_url = s3_storage.upload_bytes(
                    manifest_bytes, manifest_key, "text/xml"
                )
                _log(f"Uploaded manifest: {manifest_key}", "success")

                s3_icon_url = None
                if build.get("icon_path") and Path(build["icon_path"]).exists():
                    icon_key = s3_storage.object_key(build_uuid, "icon.png")
                    s3_icon_url = s3_storage.upload_file(
                        build["icon_path"], icon_key, "image/png"
                    )
                    _log(f"Uploaded icon: {icon_key}", "success")

                install_url = f"itms-services://?action=download-manifest&url={s3_manifest_url}"
                manifest_path = build_dir / "manifest.plist"
                manifest_path.write_bytes(manifest_bytes)
                store.update(
                    build_uuid,
                    s3_ipa_url=s3_ipa_url,
                    s3_manifest_url=s3_manifest_url,
                    s3_icon_url=s3_icon_url,
                    manifest_path=str(manifest_path),
                )
            except Exception as s3_err:
                log.exception("S3 upload failed for build %s", build_uuid)
                return _fail(f"S3 upload failed: {s3_err}")

            # ── Done ─────────────────────────────────────────────────────────
            _status(STATUS_DONE)
            store.update(build_uuid, install_url=install_url)
            _log(
                f"✅ Ready! v{build['short_version']} ({build['bundle_version']})",
                "success",
            )
            _log(f"Install URL: {install_url}")

        except Exception as e:
            log.exception("Pipeline error for build %s", build_uuid)
            _fail(f"Unexpected error: {e}")


def _make_manifest(
    ipa_url: str,
    bundle_id: str,
    bundle_version: str,
    short_version: str,
    app_name: str,
) -> dict:
    return {
        "items": [
            {
                "assets": [
                    {"kind": "software-package", "url": ipa_url},
                ],
                "metadata": {
                    "bundle-identifier": bundle_id,
                    "bundle-version": short_version or bundle_version,
                    "kind": "software",
                    "title": app_name or bundle_id,
                },
            }
        ]
    }

