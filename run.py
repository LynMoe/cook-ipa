#!/usr/bin/env python
"""Entry point for the Cook IPA — Ad Hoc OTA distribution service."""

import os
import sys
import signal
import logging
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app import create_app

app = create_app()


def _exit_on_sigterm(*_args):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _exit_on_sigterm)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug, threaded=True)
