"""
IPA Signer - Wraps zsign to re-sign IPA files on Linux.

zsign usage:
  zsign -k cert.pem -m app.mobileprovision -o signed.ipa -p p12pass -f app.ipa

For .p12 input zsign accepts it directly with -p for password.
"""

import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Callable

log = logging.getLogger(__name__)


class SigningError(Exception):
    pass


def sign_ipa(
    input_ipa: str,
    output_ipa: str,
    p12_path: str,
    p12_password: str,
    mobileprovision_path: str,
    zsign_path: str,
    bundle_id_override: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    timeout: int = 300,
    compress: bool = True,  # Enable compression by default
) -> str:
    """
    Re-sign an IPA using zsign.

    Args:
        input_ipa: Path to the original .ipa
        output_ipa: Path for the signed output .ipa
        p12_path: Path to .p12 signing certificate
        p12_password: Password for the .p12 file
        mobileprovision_path: Path to .mobileprovision file
        zsign_path: Path to the zsign binary
        bundle_id_override: If set, replace the bundle ID
        log_callback: Called with each log line
        timeout: Max seconds to wait
        compress: If True, repack with compression to reduce size

    Returns:
        Path to the signed IPA.

    Raises:
        SigningError on failure.
    """
    # Check zsign exists (using 'which' if PATH lookup needed)
    if "/" not in zsign_path:
        zsign_check = shutil.which(zsign_path)
        if not zsign_check:
            raise SigningError(f"zsign binary not found in PATH: {zsign_path}")
        zsign = zsign_check
    else:
        zsign = Path(zsign_path)
        if not zsign.exists():
            raise SigningError(f"zsign binary not found at: {zsign_path}")

    for path, label in [(input_ipa, "input IPA"), (p12_path, ".p12"), (mobileprovision_path, ".mobileprovision")]:
        if not Path(path).exists():
            raise SigningError(f"File not found ({label}): {path}")

    cmd = [
        str(zsign) if isinstance(zsign, Path) else zsign,
        "-k", p12_path,
        "-p", p12_password,
        "-m", mobileprovision_path,
        "-o", output_ipa,
        "-f",  # force overwrite
        "-z", "9" if compress else "0",  # compression level: 9=max, 0=none
    ]

    if bundle_id_override:
        cmd += ["-b", bundle_id_override]

    cmd.append(input_ipa)

    _log(log_callback, f"Running zsign on {Path(input_ipa).name}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise SigningError(f"zsign timed out after {timeout}s")
    except Exception as e:
        raise SigningError(f"zsign execution failed: {e}")

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    for line in (stdout + "\n" + stderr).splitlines():
        if line.strip():
            _log(log_callback, f"[zsign] {line}")
            log.debug("[zsign] %s", line)

    if proc.returncode != 0:
        raise SigningError(
            f"zsign exited with code {proc.returncode}. "
            f"stderr: {stderr[:500]}"
        )

    if not Path(output_ipa).exists():
        raise SigningError("zsign succeeded but output IPA not found")

    size_mb = Path(output_ipa).stat().st_size / (1024 * 1024)
    _log(log_callback, f"Signing complete. Output: {output_ipa} ({size_mb:.1f} MB)")
    return output_ipa


def _log(callback: Optional[Callable], message: str):
    if callback:
        callback(message)
