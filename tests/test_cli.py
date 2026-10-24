from io import StringIO
from unittest.mock import Mock
import pytest
from rich.console import Console
from organizer.cli import main
from organizer.models import Classification
from organizer.classifier import ClassificationError


@pytest.fixture
def cli(tmp_path, monkeypatch):
    (tmp_path / "invoice.txt").write_text("Invoice total 100")
    classifier = Mock(return_value=Classification(category="Finance", reason="Invoice"))
    monkeypatch.setattr("organizer.cli.OllamaClassifier.classify", classifier)
    out = StringIO()
    return tmp_path, Console(file=out, width=120), out, classifier


def test_dry_run_never_prompts(cli, monkeypatch):
    path, console, out, _ = cli
    prompt = Mock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr("organizer.cli.Confirm.ask", prompt)
    assert main([str(path), "--dry-run", "--output", str(path / "out")], console=console) == 0
    assert (path / "invoice.txt").exists()
    assert not (path / "out").exists()
    assert "Finance" in out.getvalue()
    prompt.assert_not_called()


@pytest.mark.parametrize("response", [False, True])
def test_confirmation(cli, monkeypatch, response):
    path, console, _, _ = cli
    monkeypatch.setattr("organizer.cli.Confirm.ask", Mock(return_value=response))
    assert main([str(path)], console=console) == 0
    assert (path / "invoice.txt").exists() is not response
    assert (path / "Finance" / "invoice.txt").exists() is response


def test_eof_cancels(cli, monkeypatch):
    path, console, _, _ = cli
    monkeypatch.setattr("organizer.cli.Confirm.ask", Mock(side_effect=EOFError))
    assert main([str(path)], console=console) == 0
    assert (path / "invoice.txt").exists()


def test_empty_without_ollama(tmp_path, monkeypatch):
    classifier = Mock(side_effect=AssertionError("should not call"))
    monkeypatch.setattr("organizer.cli.OllamaClassifier", classifier)
    assert main([str(tmp_path)]) == 0


def test_ollama_failure_preserves_files(cli, monkeypatch):
    path, console, out, classifier = cli
    classifier.side_effect = ClassificationError("Start ollama serve")
    prompt = Mock()
    monkeypatch.setattr("organizer.cli.Confirm.ask", prompt)
    assert main([str(path)], console=console) == 1
    assert "ollama serve" in out.getvalue()
    assert (path / "invoice.txt").exists()
    prompt.assert_not_called()


def test_invalid_directory(tmp_path):
    assert main([str(tmp_path / "missing")]) == 1


def test_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_invalid_limit(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--max-chars", "0"])
    assert exc.value.code == 2


def test_move_failure_reported(cli, monkeypatch):
    path, console, out, _ = cli
    monkeypatch.setattr("organizer.cli.Confirm.ask", Mock(return_value=True))
    monkeypatch.setattr("organizer.cli.move_file", Mock(side_effect=PermissionError("Denied")))
    assert main([str(path)], console=console) == 1
    assert "Failed: 1" in out.getvalue()
    assert (path / "invoice.txt").exists()


def test_corrupt_document_stops_before_prompt(cli, monkeypatch):
    path, console, _, _ = cli
    (path / "bad.pdf").write_text("invalid")
    prompt = Mock()
    monkeypatch.setattr("organizer.cli.Confirm.ask", prompt)
    assert main([str(path)], console=console) == 1
    prompt.assert_not_called()
    assert (path / "invoice.txt").exists()
