"""Preview first; use exclusive destination creation and descriptor-relative I/O."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import os
import shutil
import stat

from organizer.models import Category, Classification
from organizer.scanner import safe_path, validate_directory


@dataclass(frozen=True)
class Fingerprint:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> "Fingerprint":
        if not stat.S_ISREG(value.st_mode):
            raise ValueError("Source must be a regular file, not a directory or symlink")
        return cls(value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def fingerprint(path: Path) -> Fingerprint:
    return Fingerprint.from_stat(safe_path(path).lstat())


@dataclass(frozen=True)
class PlanItem:
    source: Path
    destination: Path
    classification: Classification
    original: Fingerprint


def validate_output(path: Path) -> Path:
    path = safe_path(path)
    for parent in (path, *path.parents):
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"Output path component is not a directory: {parent}")
    return path


def plan_item(source: Path, output: Path, classification: Classification,
              original: Fingerprint | None = None,
              reserved: set[Path] | None = None) -> PlanItem:
    source = safe_path(source)
    original = original or fingerprint(source)
    category = Category(classification.category)
    directory = validate_output(output) / category.value
    validate_output(directory)
    destination = directory / source.name
    counter = 0
    while os.path.lexists(destination) or destination in (reserved or set()):
        counter += 1
        destination = directory / f"{source.stem}_{counter}{source.suffix}"
    return PlanItem(source, destination, classification, original)


@contextmanager
def open_directory(path: Path, create: bool = False) -> Iterator[int]:
    """Walk from the filesystem root with no-follow opens at every component."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("Safe movement requires POSIX directory descriptors (macOS/Linux). Use --dry-run on this platform.")
    path = safe_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def move_file(item: PlanItem, source_root: Path, output_root: Path, *,
              confirmed: bool = False, dry_run: bool = False) -> Path:
    """Copy exclusively, verify, then unlink; a failed deletion retains both copies.

    There is no multi-file transaction. Never remove an incomplete destination on
    error: retaining it avoids deleting a concurrently replaced file. Report its
    path so the user can inspect it. Source deletion happens only after fsync.
    """
    if dry_run:
        return item.destination
    if confirmed is not True:
        raise PermissionError("Explicit confirmation is required before moving files")
    source_root = validate_directory(source_root)
    output_root = validate_output(output_root)
    source = safe_path(item.source)
    destination = safe_path(item.destination)
    category = Category(item.classification.category)
    if source.parent != source_root:
        raise ValueError("Source is outside the selected directory")
    if destination.parent != output_root / category.value or destination.name in {"", ".", ".."}:
        raise ValueError("Destination is outside its predefined category directory")
    if fingerprint(source) != item.original:
        raise ValueError("Source changed since analysis; run the organizer again")
    with open_directory(source_root) as source_dir:
        with open_directory(destination.parent, create=True) as dest_dir:
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(source.name, flags, dir_fd=source_dir), "rb") as reader:
                original_stat = os.fstat(reader.fileno())
                if Fingerprint.from_stat(original_stat) != item.original:
                    raise ValueError("Source changed since analysis")
                # O_EXCL prevents overwriting any file, including dangling symlinks.
                dest_fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                  | os.O_NOFOLLOW, 0o600, dir_fd=dest_dir)
                try:
                    with os.fdopen(dest_fd, "wb") as writer:
                        shutil.copyfileobj(reader, writer)
                        writer.flush()
                        os.fchmod(writer.fileno(), stat.S_IMODE(original_stat.st_mode) & 0o777)
                        os.utime(writer.fileno(), ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                        os.fsync(writer.fileno())
                        written = os.fstat(writer.fileno())
                    if Fingerprint.from_stat(os.fstat(reader.fileno())) != item.original:
                        raise ValueError("Source changed during copying")
                    current = os.stat(source.name, dir_fd=source_dir, follow_symlinks=False)
                    if Fingerprint.from_stat(current) != item.original:
                        raise ValueError("Source was replaced during copying")
                    target = os.stat(destination.name, dir_fd=dest_dir, follow_symlinks=False)
                    if (target.st_dev, target.st_ino, target.st_size) != (written.st_dev, written.st_ino, item.original.size):
                        raise ValueError("Destination changed during copying")
                    # Validate visible directories again before deleting the source.
                    safe_path(source_root)
                    if not os.path.samestat(source_root.stat(), os.fstat(source_dir)):
                        raise ValueError("Source directory changed during copying")
                    safe_path(destination)
                    if not os.path.samestat(destination.parent.stat(), os.fstat(dest_dir)):
                        raise ValueError("Destination directory changed during copying")
                    os.unlink(source.name, dir_fd=source_dir)
                except (OSError, ValueError) as exc:
                    raise OSError(f"Move incomplete; inspect retained destination {destination}. {exc}") from exc
    return destination
