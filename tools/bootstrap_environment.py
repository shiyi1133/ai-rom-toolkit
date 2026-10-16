"""Install pinned official host dependencies into this checkout only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ":" in normalized or ".." in parts:
        raise ValueError(f"Unsafe archive member: {name!r}")
    return normalized


def verify_archive(path: Path, expected: str) -> None:
    if len(expected) != 64 or sha256(path) != expected:
        raise ValueError(f"Archive SHA-256 mismatch: {path.name}; existing file preserved")


def download(spec: dict, cache: Path) -> Path:
    archive = cache / spec["archive_name"]
    if archive.exists():
        verify_archive(archive, spec["sha256"])
        return archive
    if not spec["url"].startswith("https://"):
        raise ValueError("Dependency URL must use HTTPS")
    part = cache / (archive.name + ".part-" + uuid.uuid4().hex)
    try:
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "AI-ROM-Toolkit/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, part.open("xb") as out:
            shutil.copyfileobj(response, out)
        verify_archive(part, spec["sha256"])
        if archive.exists():
            verify_archive(archive, spec["sha256"])
        else:
            part.rename(archive)
        return archive
    finally:
        if part.exists():
            part.unlink()


def extract_archive(archive: Path, stage: Path, kind: str) -> None:
    if kind == "zip":
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                checked_member(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Archive symlinks are not accepted")
            package.extractall(stage)
    elif kind == "7z":
        tar = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/tar.exe"
        if not tar.is_file():
            raise RuntimeError("Windows tar.exe is required for the official mGBA 7z archive")
        listing = subprocess.run([str(tar), "-tf", str(archive)], check=True, capture_output=True, text=True)
        for name in listing.stdout.splitlines():
            checked_member(name)
        subprocess.run([str(tar), "-xf", str(archive), "-C", str(stage)], check=True)
    elif kind == "tar.xz":
        if not hasattr(tarfile, 'data_filter'):
            raise RuntimeError('Safe tar extraction requires Python 3.12+ on Linux')
        with tarfile.open(archive, 'r:xz') as package:
            # Validate the whole listing before writing; the data filter also
            # confines symlink/hardlink destinations and rejects special files.
            members = package.getmembers()
            for member in members:
                if member.name in ('.', './') and member.isdir():
                    continue
                checked_member(member.name)
                tarfile.data_filter(member, str(stage))
            package.extractall(stage, members=members, filter='data')
    elif kind == "appimage":
        # A pinned official binary, retained intact with its bundled licenses.
        target = stage / 'mgba.AppImage'
        shutil.copyfile(archive, target)
        target.chmod(0o755)
    else:
        raise ValueError(f"Unsupported archive kind: {kind}")


def installed(spec: dict, target: Path) -> bool:
    if not target.exists():
        return False
    marker = target / ".dependency.json"
    if not marker.is_file():
        raise ValueError(f"Existing {target.name} directory has no install marker; refusing to overwrite")
    record = json.loads(marker.read_text(encoding="utf-8-sig"))
    if record.get("id") != spec["id"] or record.get("archive_sha256") != spec["sha256"]:
        raise ValueError(f"Existing {target.name} belongs to another dependency version")
    for relative in spec["entrypoints"]:
        expected = record.get("entrypoints", {}).get(relative)
        path = target / relative
        if not expected or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Installed dependency entry changed: {spec['id']}/{relative}")
        if spec.get('executable') and not os.access(path, os.X_OK):
            raise ValueError(f'Installed entry is not executable: {relative}')
    return True


def install(spec: dict, cache: Path, runtime: Path) -> str:
    target = runtime / spec["directory"]
    if installed(spec, target):
        return "verified_existing"
    archive = download(spec, cache)
    stage = Path(tempfile.mkdtemp(prefix=".stage-" + spec["id"] + "-", dir=runtime))
    try:
        extract_archive(archive, stage, spec["format"])
        payload = stage
        for _ in range(spec.get("strip_components", 0)):
            children = list(payload.iterdir())
            if len(children) != 1 or not children[0].is_dir():
                raise ValueError("Unexpected archive root layout")
            payload = children[0]
        for relative in spec["entrypoints"]:
            if not (payload / relative).is_file():
                raise ValueError(f"Missing dependency entrypoint: {relative}")
            if spec.get('executable') and not os.access(payload / relative, os.X_OK):
                raise ValueError(f'Dependency entry is not executable: {relative}')
        record = {
            "id": spec["id"], "version": spec["version"], "archive_sha256": spec["sha256"],
            "entrypoints": {name: sha256(payload / name) for name in spec["entrypoints"]},
        }
        (payload / ".dependency.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"Target appeared during initialization: {target}")
        payload.rename(target)
        return "installed"
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache")
    args = parser.parse_args()
    from toolkit_host import require_supported_host, runtime_root
    host = require_supported_host()
    lock_name = 'dependencies.linux.lock.json' if host == 'linux' else 'dependencies.lock.json'
    lock = json.loads((ROOT / lock_name).read_text(encoding="utf-8"))
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    runtime = runtime_root()
    runtime.mkdir(parents=True, exist_ok=True)
    outcomes = {}
    for spec in lock["dependencies"]:
        print(f"Checking {spec['id']} {spec['version']}...", flush=True)
        outcomes[spec["id"]] = install(spec, cache, runtime)
    print(json.dumps({"core_dependencies": outcomes, "optional_headless": "not_provided_by_repository"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
