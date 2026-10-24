from pathlib import Path
import pytest
from organizer.scanner import scan, safe_path


def test_scan_supported_nonrecursive(tmp_path):
    for name in ["a.PDF", "b.docx", "c.txt", "photo.jpg"]:
        (tmp_path / name).touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hidden.txt").touch()
    (tmp_path / "link.txt").symlink_to(tmp_path / "c.txt")
    result = scan(tmp_path)
    assert [p.name for p in result.files] == ["a.PDF", "b.docx", "c.txt"]
    assert len(result.skipped) == 3


def test_empty(tmp_path):
    assert scan(tmp_path).files == []


def test_missing(tmp_path):
    with pytest.raises(ValueError):
        scan(tmp_path / "missing")


def test_symlink_directory(tmp_path):
    (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        scan(tmp_path / "alias")


def test_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path / ".." / "anything")
