import logging
from flask import Flask
from flask_cors import CORS

log = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="../static")

    from config import Config
    app.config.from_object(Config)
    Config.log_credential_paths()

    CORS(app)

    # Ensure directories exist
    for d in [Config.BUILDS_DIR, Config.CERTS_DIR, Config.PROFILE_CACHE_DIR]:
        import pathlib
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)

    # Register blueprints (OTA distribution is via S3 only; no local /manifest, /ipa, /install)
    from app.routes.upload   import upload_bp
    from app.routes.builds   import builds_bp
    from app.routes.devices  import devices_bp
    from app.routes.profiles import profiles_bp
    from app.routes.main     import main_bp

    app.register_blueprint(upload_bp,   url_prefix="/api")
    app.register_blueprint(builds_bp,   url_prefix="/api")
    app.register_blueprint(devices_bp,  url_prefix="/api")
    app.register_blueprint(profiles_bp, url_prefix="/api")
    app.register_blueprint(main_bp)  # SPA fallback last

    log.info("App created. Blueprints registered.")
    return app

