"""Stream the study inputs into immutable raw files and verify their manifest."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile

_ARCHIVE = "https://archive.opentransportdata.swiss/istdaten"
_SERVICE_NAME = "actual-date-swiss-service-point.csv"
_SERVICE_URL = (
    "https://data.opentransportdata.swiss/dataset/39e5f264-257a-4f3f-bccc-5322c37058c5/"
    "resource/38ae9c04-05e4-4420-8c56-250ac6f4eb2f/download/" + _SERVICE_NAME
)
_SOURCE = "opentransportdata.swiss"
_TERMS = "Open use. Must provide the source."
_BUFFER_BYTES = 1024 * 1024


def _archive_url(month: str) -> str:
    return f"{_ARCHIVE}/{month[:4]}/ist-daten-v2-{month}.zip"


def _fetch(url: str, target: Path) -> None:
    with urlopen(url, timeout=120) as response, target.open("xb") as output:
        shutil.copyfileobj(response, output, _BUFFER_BYTES)
        size = response.headers.get("Content-Length")
    if size is not None and target.stat().st_size != int(size):
        raise OSError(f"Incomplete download from {url}")


def _sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _entries(manifest_path: Path) -> dict[str, dict]:
    if not manifest_path.exists():
        return {}
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    return {entry["path"]: entry for entry in entries}


def _matches(path: Path, entry: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == entry["bytes"]
        and _sha256(path) == entry["sha256"]
    )


def _verified(target: Path, data_dir: Path, entries: dict[str, dict]) -> bool:
    entry = entries.get(target.relative_to(data_dir).as_posix())
    if entry is None or not target.exists():
        return False
    if not _matches(target, entry):
        raise ValueError(f"Checksum mismatch in existing raw file: {target}")
    if target.stat().st_mode & 0o222:
        raise ValueError(f"Existing raw file is writable: {target}")
    return True


def _publish(staged: Path, target: Path, expected: dict | None) -> None:
    if expected is not None and not _matches(staged, expected):
        raise ValueError(f"Downloaded data differs from the manifest: {target}")
    staged.chmod(0o444)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.hardlink_to(staged)
    except FileExistsError:
        if not target.is_file() or _sha256(staged) != _sha256(target):
            raise ValueError(f"Existing raw file differs from source: {target}") from None
        if target.stat().st_mode & 0o222:
            raise ValueError(f"Existing raw file is writable: {target}") from None


def download_ist_daten(start: date, end: date, raw_dir: Path, dry_run: bool = False) -> list[Path]:
    """Download inclusive daily CSVs and their ZIPs into raw_dir; return the CSV paths.

    A dry run prints one archive URL per month and returns canonical lookup paths.
    Downloads preserve the actual ZIP member basename, including its original casing.
    """
    if end < start:
        raise ValueError("Period end must be on or after its start")
    directory = raw_dir / "ist-daten"
    months: dict[str, list[str]] = {}
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        months.setdefault(day.isoformat()[:7], []).append(f"{day.isoformat()}_istdaten.csv")
    if dry_run:
        for month in months:
            print(_archive_url(month))
        return [directory / name for names in months.values() for name in names]

    data_dir = raw_dir.parent
    entries = _entries(data_dir / "MANIFEST.json")
    downloaded = []
    for month, names in months.items():
        url = _archive_url(month)
        archive = directory / url.rsplit("/", 1)[-1]
        have_archive = _verified(archive, data_dir, entries)
        data_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".ist-daten-", dir=data_dir) as tmp:
            staging = Path(tmp)
            zip_path = archive if have_archive else staging / archive.name
            if not have_archive:
                _fetch(url, zip_path)
            with ZipFile(zip_path) as bundle:
                wanted = set(names)
                members = {}
                for member in bundle.infolist():
                    key = PurePosixPath(member.filename).name.lower()
                    if key in wanted and not member.is_dir():
                        if key in members:
                            raise ValueError(f"Duplicate archive member: {key}")
                        members[key] = member
                if absent := wanted - members.keys():
                    raise ValueError(f"Missing archive members: {', '.join(sorted(absent))}")
                missing = []
                for name in names:
                    member = members[name]
                    path = directory / PurePosixPath(member.filename).name
                    downloaded.append(path)
                    if _verified(path, data_dir, entries):
                        continue
                    missing.append(path)
                    with bundle.open(member) as src, (staging / path.name).open("xb") as dst:
                        shutil.copyfileobj(src, dst, _BUFFER_BYTES)
            if not have_archive:
                _publish(zip_path, archive, entries.get(archive.relative_to(data_dir).as_posix()))
            for path in missing:
                _publish(
                    staging / path.name, path, entries.get(path.relative_to(data_dir).as_posix())
                )
    return downloaded


def download_service_points(raw_dir: Path, dry_run: bool = False) -> Path:
    """Download the atlas v2 CSV under raw_dir and return its destination path."""
    target = raw_dir / "service-points" / _SERVICE_NAME
    if dry_run:
        print(_SERVICE_URL)
        return target
    data_dir = raw_dir.parent
    entries = _entries(data_dir / "MANIFEST.json")
    if not _verified(target, data_dir, entries):
        data_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".service-points-", dir=data_dir) as tmp:
            staged = Path(tmp) / target.name
            _fetch(_SERVICE_URL, staged)
            _publish(staged, target, entries.get(target.relative_to(data_dir).as_posix()))
    return target


def write_manifest(files: list[Path], manifest_path: Path) -> None:
    """Write SHA-256, byte length, source URL and UTC publication time per raw file.

    Manifest paths are relative to the directory containing the manifest.
    """
    existing = _entries(manifest_path)
    data_dir = manifest_path.parent.resolve()
    # Preserve prior periods and include the monthly ZIPs corresponding to daily CSVs.
    selected = {path.resolve() for path in files}
    for path in files:
        if path.suffix.lower() == ".csv" and path.parent.name == "ist-daten":
            archive = path.with_name(f"ist-daten-v2-{path.name[:7]}.zip")
            if archive.is_file():
                selected.add(archive.resolve())
    for path in sorted(selected):
        relative = path.relative_to(data_dir).as_posix()
        if relative in existing:
            if not _matches(path, existing[relative]):
                raise ValueError(f"Checksum mismatch in existing raw file: {path}")
            continue
        stat = path.stat()
        if path.name == _SERVICE_NAME:
            url = _SERVICE_URL
        elif path.suffix == ".zip":
            url = _archive_url(path.stem[-7:])
        elif path.parent.name == "ist-daten":
            url = _archive_url(path.name[:7])
        else:
            raise ValueError(f"Unknown source for raw file: {path}")
        existing[relative] = {
            "path": relative,
            "url": url,
            "sha256": _sha256(path),
            "bytes": stat.st_size,
            "downloaded_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        }

    manifest = {
        "files": [existing[key] for key in sorted(existing)],
        "source": _SOURCE,
        "terms": _TERMS,
    }
    with TemporaryDirectory(prefix=".manifest-", dir=data_dir) as tmp:
        staged = Path(tmp) / manifest_path.name
        staged.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        staged.replace(manifest_path)


def verify_manifest(manifest_path: Path) -> list[str]:
    """Return sorted manifest-relative paths of missing or mismatching files."""
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    entries = _entries(manifest_path)
    return [
        path
        for path, entry in sorted(entries.items())
        if not _matches(manifest_path.parent / path, entry)
    ]
