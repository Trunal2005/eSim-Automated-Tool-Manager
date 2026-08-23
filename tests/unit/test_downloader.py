"""Unit tests for the downloader."""

import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

import pytest

from esim_tool_manager.infra.downloader import (
    ChecksumMismatchError,
    DownloadError,
    compute_checksum,
    download_file,
)


class TestComputeChecksum:
    """Tests for local file checksum computation."""

    def test_compute_checksum(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        content = b"hello world"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        actual = compute_checksum(test_file)
        assert actual == expected

    def test_compute_checksum_empty_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()
        actual = compute_checksum(test_file)
        assert actual == expected


class TestDownloadFile:
    """Tests for the download function."""

    def test_download_invalid_url(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with pytest.raises(DownloadError):
            download_file("http://invalid.localhost.test/file.txt", dest, timeout=3)

    def test_download_creates_parent_dirs(self, tmp_path: Path) -> None:
        # Even though the download will fail, parent dirs should be created
        dest = tmp_path / "nested" / "dir" / "output.txt"
        with pytest.raises(DownloadError):
            download_file("http://invalid.localhost.test/file.txt", dest, timeout=3)
        assert dest.parent.exists()
