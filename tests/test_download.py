"""Offline tests for the archive downloader and checksummed manifest."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from stat import S_IMODE
from zipfile import ZipFile

import pytest

from urban_computing.data import download

_START = date(2026, 10, 11)
_END = date(2026, 10, 12)


@pytest.fixture
def source(monkeypatch):
    """Provide a two-day archive, an out-of-period member and a service-point CSV."""
    fetched = []

    def fake_fetch(url, target):
        fetched.append(url)
        if url.endswith(".zip"):
            with ZipFile(target, "w") as bundle:
                bundle.writestr("2026-10-11_IstDaten.csv", "fixture day 11\n")
                bundle.writestr("2026-10-12_istdaten.csv", "fixture day 12\n")
                bundle.writestr("2026-10-29_IstDaten.csv", "outside study range\n")
        else:
            target.write_bytes(b"service points\n")

    monkeypatch.setattr(download, "_fetch", fake_fetch)
    return fetched


def _run(data_dir):
    raw = data_dir / "raw"
    files = download.download_ist_daten(_START, _END, raw)
    files.append(download.download_service_points(raw))
    manifest = data_dir / "MANIFEST.json"
    download.write_manifest(files, manifest)
    return manifest


def test_download_and_resume(tmp_path, source):
    manifest = _run(tmp_path)
    assert len(source) == 2
    assert download.verify_manifest(manifest) == []
    original = manifest.read_bytes()
    files = {entry["path"]: entry for entry in json.loads(original)["files"]}
    assert set(files) == {
        "raw/ist-daten/2026-10-11_IstDaten.csv",
        "raw/ist-daten/2026-10-12_istdaten.csv",
        "raw/ist-daten/ist-daten-v2-2026-10.zip",
        "raw/service-points/actual-date-swiss-service-point.csv",
    }
    assert all(S_IMODE((tmp_path / path).stat().st_mode) == 0o444 for path in files)
    assert all(
        set(entry) == {"path", "url", "sha256", "bytes", "downloaded_at"}
        for entry in files.values()
    )
    assert _run(tmp_path).read_bytes() == original

    daily = tmp_path / "raw/ist-daten/2026-10-11_IstDaten.csv"
    daily.unlink()
    assert download.verify_manifest(manifest) == ["raw/ist-daten/2026-10-11_IstDaten.csv"]
    assert _run(tmp_path).read_bytes() == original
    assert download.verify_manifest(manifest) == []
    assert len(source) == 2


def test_tampered_file_is_reported_and_never_overwritten(tmp_path, source):
    manifest = _run(tmp_path)
    path = "raw/ist-daten/2026-10-11_IstDaten.csv"
    target = tmp_path / path
    target.chmod(0o644)
    target.write_bytes(b"fixture day XX\n")  # same byte length
    assert download.verify_manifest(manifest) == [path]
    with pytest.raises(ValueError, match="Checksum mismatch"):
        _run(tmp_path)
    assert target.read_bytes() == b"fixture day XX\n"
    assert len(source) == 2


def test_missing_zip_member_publishes_no_raw_files(tmp_path, source):
    raw = tmp_path / "raw"
    with pytest.raises(ValueError, match="Missing archive members"):
        download.download_ist_daten(date(2026, 10, 10), _END, raw)
    assert len(source) == 1
    assert not raw.exists()


def test_changed_service_point_snapshot_is_not_published(tmp_path, source, monkeypatch):
    manifest = _run(tmp_path)
    relative = "raw/service-points/actual-date-swiss-service-point.csv"
    target = tmp_path / relative
    target.unlink()

    def fetch_changed_snapshot(url, staged):
        staged.write_bytes(b"new service points\n")

    monkeypatch.setattr(download, "_fetch", fetch_changed_snapshot)
    with pytest.raises(ValueError, match="Downloaded data differs from the manifest"):
        download.download_service_points(tmp_path / "raw")
    assert not target.exists()
    assert download.verify_manifest(manifest) == [relative]


def test_cli_dry_run_and_verify(tmp_path, source):
    script = Path(__file__).resolve().parents[1] / "scripts" / "download_data.py"
    cli = [sys.executable, str(script), "--data-dir", str(tmp_path)]
    result = subprocess.run(
        [*cli, "--period", "2026-10-01:2026-10-28", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "https://archive.opentransportdata.swiss/istdaten/2026/ist-daten-v2-2026-10.zip",
        "https://data.opentransportdata.swiss/dataset/39e5f264-257a-4f3f-bccc-5322c37058c5/"
        "resource/38ae9c04-05e4-4420-8c56-250ac6f4eb2f/download/"
        "actual-date-swiss-service-point.csv",
    ]
    assert not list(tmp_path.iterdir())

    _run(tmp_path)
    subprocess.run([*cli, "--verify"], check=True, capture_output=True)
    (tmp_path / "raw/ist-daten/2026-10-11_IstDaten.csv").unlink()
    bad = subprocess.run([*cli, "--verify"], capture_output=True, text=True, check=False)
    assert bad.returncode == 1
    assert "raw/ist-daten/2026-10-11_IstDaten.csv" in bad.stdout
