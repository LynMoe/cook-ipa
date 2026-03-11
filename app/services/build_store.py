"""
JSON-based build storage.
Each build lives in builds/<uuid>/ with:
  metadata.json  — build state and IPA metadata
  original.ipa   — uploaded file (deleted after signing if disk is tight)
  signed.ipa     — re-signed IPA
  manifest.plist — OTA manifest
  icon.png       — app icon (optional)
  build.log      — JSONL file, one log entry per line
"""
import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

log = logging.getLogger(__name__)

# UUID validation regex to prevent path traversal attacks
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def _validate_uuid(uuid: str) -> bool:
    """Validate UUID format to prevent path traversal attacks."""
    return bool(UUID_PATTERN.match(uuid.lower()))

STATUS_PENDING   = "pending"
STATUS_ANALYZING = "analyzing"
STATUS_SIGNING   = "signing"
STATUS_DONE      = "done"
STATUS_FAILED    = "failed"


class BuildStore:
    def __init__(self, builds_dir: Path):
        self.builds_dir = Path(builds_dir)
        self.builds_dir.mkdir(parents=True, exist_ok=True)

    def create(self, uuid: str, original_filename: str, original_ipa_path: str) -> dict:
        build_dir = self.builds_dir / uuid
        build_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "uuid": uuid,
            "original_filename": original_filename,
            "original_ipa_path": original_ipa_path,
            "bundle_id": None,
            "bundle_version": None,
            "short_version": None,
            "app_name": None,
            "signed_ipa_path": None,
            "manifest_path": None,
            "icon_path": None,
            "status": STATUS_PENDING,
            "error_message": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._write_meta(uuid, meta)
        return meta

    def get(self, uuid: str) -> Optional[dict]:
        if not _validate_uuid(uuid):
            log.warning(f"Invalid UUID format: {uuid}")
            return None
        meta_path = self.builds_dir / uuid / "metadata.json"
        
        # Validate that resolved path is within builds_dir to prevent traversal
        try:
            resolved = meta_path.resolve()
            if not str(resolved).startswith(str(self.builds_dir.resolve())):
                log.error(f"Path traversal attempt detected: {uuid}")
                return None
        except Exception as e:
            log.error(f"Path resolution failed for {uuid}: {e}")
            return None
        
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def update(self, uuid: str, **kwargs) -> dict:
        meta = self.get(uuid) or {}
        meta.update(kwargs)
        meta["updated_at"] = datetime.utcnow().isoformat()
        self._write_meta(uuid, meta)
        return meta

    def list_all(self, page: int = 1, per_page: int = 50) -> Tuple[List[dict], int]:
        builds = []
        for d in self.builds_dir.iterdir():
            if d.is_dir():
                meta = self.get(d.name)
                if meta:
                    builds.append(meta)
        builds.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        total = len(builds)
        start = (page - 1) * per_page
        return builds[start : start + per_page], total

    def append_log(self, uuid: str, message: str, level: str = "info") -> dict:
        log_path = self.builds_dir / uuid / "build.log"
        # Use millisecond timestamp as monotonic ID — avoids reading the whole file
        entry = {
            "id": int(time.time() * 1000),
            "level": level,
            "message": message,
            "created_at": datetime.utcnow().isoformat(),
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def read_logs(self, uuid: str, since_id: int = 0) -> List[dict]:
        log_path = self.builds_dir / uuid / "build.log"
        if not log_path.exists():
            return []
        entries = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                if e.get("id", 0) > since_id:
                    entries.append(e)
            except Exception:
                pass
        return entries

    def delete(self, uuid: str) -> bool:
        import shutil
        build_dir = self.builds_dir / uuid
        if build_dir.exists():
            shutil.rmtree(build_dir)
            return True
        return False

    def build_dir(self, uuid: str) -> Path:
        return self.builds_dir / uuid

    def to_api_dict(self, meta: dict, base_url: str = "") -> dict:
        """Convert metadata to API response dict. OTA URLs come from S3 (s3_*_url, install_url)."""
        d = dict(meta)
        if meta.get("status") == STATUS_DONE and meta.get("s3_manifest_url"):
            d["manifest_url"] = meta.get("s3_manifest_url")
            d["ipa_url"] = meta.get("s3_ipa_url")
            d["install_url"] = meta.get("install_url") or ""
            d["icon_url"] = meta.get("s3_icon_url") or ""
            d["has_manifest"] = True
        else:
            d["has_manifest"] = False
            d["manifest_url"] = None
            d["ipa_url"] = None
            d["install_url"] = meta.get("install_url")
            d["icon_url"] = None
        return d

    def _write_meta(self, uuid: str, meta: dict):
        meta_path = self.builds_dir / uuid / "metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


# Singleton — initialized lazily on first use
_store: Optional[BuildStore] = None
_store_lock = threading.Lock()


def get_store() -> BuildStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                from config import Config
                _store = BuildStore(Config.BUILDS_DIR)
    return _store
