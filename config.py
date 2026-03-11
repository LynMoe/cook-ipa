import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # Directories (CERTS_DIR can be overridden by env e.g. in Docker to /app/certs)
    BUILDS_DIR = Path(os.environ.get("BUILDS_DIR", str(BASE_DIR / "builds")))
    CERTS_DIR  = Path(os.environ.get("CERTS_DIR", str(BASE_DIR / "certs")))
    BIN_DIR    = BASE_DIR / "bin"
    PROFILE_CACHE_DIR = Path("/tmp/cook-ipa-profiles")  # Volatile profile cache

    # Apple App Store Connect API
    APPLE_KEY_ID          = os.environ.get("APPLE_KEY_ID", "")
    APPLE_ISSUER_ID       = os.environ.get("APPLE_ISSUER_ID", "")
    APPLE_PRIVATE_KEY_PATH = os.environ.get(
        "APPLE_PRIVATE_KEY_PATH", str(CERTS_DIR / "AuthKey.p8")
    )

    # IPA signing
    P12_PATH     = os.environ.get("P12_PATH", str(CERTS_DIR / "cert.p12"))
    P12_PASSWORD = os.environ.get("P12_PASSWORD", "")

    # .mobileprovision: explicit path OR auto-detect latest in certs/
    MOBILEPROVISION_PATH = os.environ.get("MOBILEPROVISION_PATH", "")

    APP_BUNDLE_ID = os.environ.get("APP_BUNDLE_ID", "")
    SERVER_BASE_URL = os.environ.get("SERVER_BASE_URL", "http://localhost:5000")

    # zsign binary (in PATH)
    ZSIGN_PATH = "zsign"  # Use system PATH

    # S3 storage for OTA artifacts (signed IPA, manifest.plist, icon)
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
    S3_REGION = os.environ.get("S3_REGION", "us-east-1")
    S3_BUCKET = os.environ.get("S3_BUCKET", "")
    S3_PREFIX = os.environ.get("S3_PREFIX", "ota").rstrip("/")
    S3_EXTERNAL_DOMAIN = os.environ.get("S3_EXTERNAL_DOMAIN", "").rstrip("/")

    @classmethod
    def s3_public_url(cls, object_key: str) -> str:
        """Build public URL for an S3 object using external domain (no trailing slash on domain)."""
        if not cls.S3_EXTERNAL_DOMAIN or not object_key:
            return ""
        return f"{cls.S3_EXTERNAL_DOMAIN}/{object_key.lstrip('/')}"

    # Max upload size: 4GB
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024 * 1024

    # SPA frontend (resolved at runtime; override with SPA_DIR env)
    SPA_DIR_ENV = os.environ.get("SPA_DIR", "")

    @classmethod
    def get_spa_dir(cls) -> Path:
        """Return SPA static root, resolved at runtime. Override with SPA_DIR env."""
        if cls.SPA_DIR_ENV:
            p = Path(cls.SPA_DIR_ENV).resolve()
            if p.is_dir():
                return p
        # Default: app/static/spa relative to project root (where config.py lives)
        return (BASE_DIR / "app" / "static" / "spa").resolve()

    @classmethod
    def log_credential_paths(cls) -> None:
        """Log credential paths and existence at startup (for debugging Docker/env)."""
        import logging
        log = logging.getLogger(__name__)
        p8 = Path(cls.APPLE_PRIVATE_KEY_PATH)
        p12 = Path(cls.P12_PATH)
        log.info(
            "Credentials: APPLE_PRIVATE_KEY_PATH=%s (exists=%s), P12_PATH=%s (exists=%s), CERTS_DIR=%s",
            cls.APPLE_PRIVATE_KEY_PATH, p8.exists(), cls.P12_PATH, p12.exists(), cls.CERTS_DIR,
        )

    @classmethod
    def get_mobileprovision_path(cls) -> str:
        """Return explicit path or auto-detect the latest .mobileprovision in /tmp cache."""
        if cls.MOBILEPROVISION_PATH and Path(cls.MOBILEPROVISION_PATH).exists():
            return cls.MOBILEPROVISION_PATH
        # Auto-detect: find the most recently modified .mobileprovision in /tmp/cook-ipa-profiles/
        profile_dir = cls.PROFILE_CACHE_DIR
        profile_dir.mkdir(parents=True, exist_ok=True)
        profiles = sorted(
            profile_dir.glob("*.mobileprovision"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return str(profiles[0]) if profiles else ""

