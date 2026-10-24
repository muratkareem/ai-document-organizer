from dataclasses import replace
import os
import pytest
from organizer.file_manager import plan_item, move_file
from organizer.models import Classification


@pytest.fixture
def planned(tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("Original contents")
    result = Classification(category="Finance", reason="Invoice")
    return plan_item(source, tmp_path / "output", result)


def execute(item, **kwargs):
    return move_file(item, item.source.parent, item.source.parent / "output", **kwargs)


def test_move(planned):
    assert execute(planned, confirmed=True).read_text() == "Original contents"
    assert not planned.source.exists()


def test_confirmation(planned):
    with pytest.raises(PermissionError):
        execute(planned)
    assert planned.source.exists()
    assert not planned.destination.parent.exists()


def test_dry_run(planned):
    execute(planned, dry_run=True, confirmed=True)
    assert planned.source.exists()
    assert not planned.destination.parent.exists()


def test_collision(planned):
    planned.destination.parent.mkdir(parents=True)
    planned.destination.write_text("Existing")
    new = plan_item(planned.source, planned.source.parent / "output", planned.classification)
    assert new.destination.name == "report_1.txt"
    execute(new, confirmed=True)
    assert planned.destination.read_text() == "Existing"


def test_collision_after_preview(planned):
    planned.destination.parent.mkdir(parents=True)
    planned.destination.write_text("Keep")
    with pytest.raises(FileExistsError):
        execute(planned, confirmed=True)
    assert planned.source.exists()
    assert planned.destination.read_text() == "Keep"


def test_missing_source(planned):
    planned.source.unlink()
    with pytest.raises(FileNotFoundError):
        execute(planned, confirmed=True)


def test_changed_source(planned):
    planned.source.write_text("Edited")
    with pytest.raises(ValueError, match="changed"):
        execute(planned, confirmed=True)
    assert not planned.destination.exists()


def test_source_replaced_by_symlink(planned):
    planned.source.unlink()
    planned.source.symlink_to("/etc/hosts")
    with pytest.raises(ValueError):
        execute(planned, confirmed=True)


def test_source_replaced_by_directory(planned):
    planned.source.unlink()
    planned.source.mkdir()
    with pytest.raises(ValueError):
        execute(planned, confirmed=True)


def test_destination_symlink(planned, tmp_path):
    planned.destination.parent.parent.mkdir()
    planned.destination.parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        execute(planned, confirmed=True)
    assert planned.source.exists()


def test_path_escape(planned, tmp_path):
    escaped = replace(planned, destination=tmp_path / "escape.txt")
    with pytest.raises(ValueError, match="outside"):
        execute(escaped, confirmed=True)


def test_outside_source(planned, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="outside"):
        move_file(planned, other, tmp_path / "output", confirmed=True)


def test_permission_failure(planned, monkeypatch):
    original = os.open
    def denied(path, flags, *args, **kwargs):
        if flags & os.O_EXCL:
            raise PermissionError("read-only output")
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(PermissionError):
        execute(planned, confirmed=True)
    assert planned.source.read_text() == "Original contents"


def test_copy_failure_preserves_source(planned, monkeypatch):
    def failed(*args):
        raise OSError("disk full")
    monkeypatch.setattr("organizer.file_manager.shutil.copyfileobj", failed)
    with pytest.raises(OSError, match="retained destination"):
        execute(planned, confirmed=True)
    assert planned.source.read_text() == "Original contents"


def test_dangling_collision(planned):
    planned.destination.parent.mkdir(parents=True)
    planned.destination.symlink_to("missing")
    new = plan_item(planned.source, planned.source.parent / "output", planned.classification)
    assert new.destination.name == "report_1.txt"
