"""Repository identity and private local storage paths."""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
from contextlib import suppress
from pathlib import Path


def git_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
        text=True,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else candidate


def repo_identity(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        check=False,
        text=True,
    )
    remote = result.stdout.strip()
    return remote or str(root.resolve())


def repo_hash(root: Path) -> str:
    return hashlib.sha256(repo_identity(root).encode()).hexdigest()[:16]


def reflex_home() -> Path:
    return Path(os.environ.get("MOSS_REFLEX_HOME", "~/.moss-reflex")).expanduser()


def repo_dir(root: Path) -> Path:
    directory = reflex_home() / repo_hash(root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with suppress(OSError):
        directory.chmod(0o700)
    return directory


def session_name(root: Path) -> str:
    directory = repo_dir(root)
    id_path = directory / "install-id"
    try:
        descriptor = os.open(id_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        install_id = id_path.read_text(encoding="utf-8").strip()
    else:
        install_id = secrets.token_hex(10)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(install_id)
    return f"reflex-{repo_hash(root)}-{install_id}"
