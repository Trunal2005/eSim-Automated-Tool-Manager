"""Secure file downloader with checksum verification.

Downloads files to a temporary directory, verifies SHA256 checksums
before moving to the final destination, and cleans up on failure.
Never executes or extracts anything without prior checksum validation.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Default chunk size for downloads (64 KB)
CHUNK_SIZE = 65536


class DownloadError(Exception):
    """Raised when a download fails or checksum verification fails."""


class ChecksumMismatchError(DownloadError):
    """Raised when the downloaded file's checksum doesn't match the expected value."""

    def __init__(self, expected: str, actual: str, url: str) -> None:
        self.expected = expected
        self.actual = actual
        self.url = url
        super().__init__(
            f"Checksum mismatch for {url}:\n"
            f"  Expected: {expected}\n"
            f"  Actual:   {actual}\n"
            f"This file may be corrupted or tampered with. "
            f"The download has been discarded."
        )


def download_file(
    url: str,
    dest: Path,
    expected_checksum: str | None = None,
    progress_callback: Callable[[int, int | None], None] | None = None,
    timeout: int = 120,
) -> Path:
    """Download a file securely with optional checksum verification.

    Downloads to a temporary file first, verifies the checksum if provided,
    then moves to the final destination. Cleans up on any failure.

    Args:
        url: URL to download from.
        dest: Final destination path for the downloaded file.
        expected_checksum: Expected SHA256 hex digest. If provided, the download
            is verified before being moved to dest. If verification fails,
            the file is deleted and a ChecksumMismatchError is raised.
        progress_callback: Optional callback(bytes_downloaded, total_bytes)
            called during download. total_bytes may be None if the server
            doesn't provide Content-Length.
        timeout: Connection/read timeout in seconds.

    Returns:
        Path to the downloaded file (same as dest).

    Raises:
        DownloadError: If the download fails for any reason.
        ChecksumMismatchError: If the checksum doesn't match.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Download to a temp file in the same directory (for atomic rename)
    tmp_dir = tempfile.mkdtemp(prefix="esim_download_")
    tmp_path = Path(tmp_dir) / dest.name

    try:
        logger.info("Downloading: %s", url)
        logger.debug("  Temp path: %s", tmp_path)
        logger.debug("  Final path: %s", dest)

        # Open the URL
        req = urllib.request.Request(url, headers={"User-Agent": "esim-tool-manager/0.1.0"})
        response = urllib.request.urlopen(req, timeout=timeout)

        # Get total size if available
        total_size: int | None = None
        content_length = response.headers.get("Content-Length")
        if content_length:
            total_size = int(content_length)

        # Download with progress tracking
        hasher = hashlib.sha256()
        downloaded = 0

        with open(tmp_path, "wb") as f:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    progress_callback(downloaded, total_size)

        logger.info("Download complete: %d bytes", downloaded)

        # Verify checksum if provided
        if expected_checksum:
            actual_checksum = hasher.hexdigest()
            if actual_checksum.lower() != expected_checksum.lower():
                raise ChecksumMismatchError(
                    expected=expected_checksum,
                    actual=actual_checksum,
                    url=url,
                )
            logger.info("Checksum verified: %s", actual_checksum[:16] + "...")

        # Move to final destination
        shutil.move(str(tmp_path), str(dest))
        logger.info("File saved to: %s", dest)
        return dest

    except ChecksumMismatchError:
        # Clean up and re-raise
        raise

    except urllib.error.URLError as e:
        raise DownloadError(
            f"Failed to download {url}: {e.reason}"
        ) from e

    except OSError as e:
        raise DownloadError(
            f"File system error during download of {url}: {e}"
        ) from e

    finally:
        # Always clean up the temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


def compute_checksum(file_path: Path) -> str:
    """Compute the SHA256 checksum of a local file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded SHA256 digest string.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
