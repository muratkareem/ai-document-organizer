"""Non-recursive discovery with explicit symlink rejection."""
from dataclasses import dataclass
from pathlib import Path
import stat

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt"}


def safe_path(path: Path) -> Path:
    """Return an absolute path, rejecting traversal and existing symlink components."""
    path = path.expanduser()
    if ".." in path.parts:
        raise ValueError("Parent traversal (..) is not allowed; use an absolute path.")
    path = path.absolute()
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise ValueError(f"Symlink paths are not allowed: {component}")
    return path


def validate_directory(path: Path) -> Path:
    path = safe_path(path)
    if not path.is_dir():
        raise ValueError(f"Not an existing directory: {path}")
    return path


@dataclass(frozen=True)
class ScanResult:
    files: list[Path]
    skipped: list[tuple[Path, str]]


def scan(directory: Path) -> ScanResult:
    directory = validate_directory(directory)
    files, skipped = [], []
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            skipped.append((path, "symlink"))
        elif not stat.S_ISREG(mode):
            skipped.append((path, "directory or non-regular file (not scanned)"))
        elif path.suffix.lower() not in SUPPORTED_SUFFIXES:
            skipped.append((path, "unsupported format"))
        else:
            files.append(path)
    return ScanResult(files, skipped)
