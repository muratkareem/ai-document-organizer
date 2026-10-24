"""Preview, confirm, and organize documents with a readable Rich interface."""
import argparse
import logging
from pathlib import Path
from rich.console import Console
from rich.progress import track
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from organizer.classifier import ClassificationError, OllamaClassifier
from organizer.extractor import ExtractionError, extract_text
from organizer.file_manager import fingerprint, move_file, plan_item, validate_output
from organizer.scanner import scan, validate_directory

logger = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Classify local PDF, DOCX, and TXT documents with Ollama, preview, then confirm moves.")
    result.add_argument("directory", type=Path, help="Source directory (non-recursive)")
    result.add_argument("--output", type=Path, help="Destination root (default: source directory)")
    result.add_argument("--dry-run", action="store_true", help="Show the plan without creating folders or moving files")
    result.add_argument("--model", default="qwen2.5:7b", help="Installed Ollama model (default: qwen2.5:7b)")
    result.add_argument("--max-chars", type=positive_int, default=6000, help="Maximum extracted text characters per document (default: 6000)")
    result.add_argument("--timeout", type=positive_int, default=120, help="Seconds per Ollama request (default: 120; one retry)")
    return result


def run(args: argparse.Namespace, console: Console) -> int:
    source = validate_directory(args.directory)
    output = validate_output(args.output or source)
    console.print("AI Document Organizer", style="bold cyan")
    console.rule()
    console.print(Text(f"Scanning: {source}"))
    found = scan(source)
    for path, reason in found.skipped:
        console.print(Text(f"Skipped {path.name}: {reason}", style="dim"))
    if not found.files:
        console.print("No supported documents found.")
        return 0
    console.print(f"Found {len(found.files)} supported documents.")
    classifier = OllamaClassifier(args.model, args.max_chars, args.timeout)
    plan = []
    reserved: set[Path] = set()
    console.print("Analyzing documents with Ollama...")
    for path in track(found.files, description="Analyzing", console=console):
        original = fingerprint(path)
        extracted = extract_text(path, args.max_chars)
        if extracted.warning:
            console.print(Text(f"{path.name}: {extracted.warning}", style="yellow"))
        classification = classifier.classify(path.name, extracted.text)
        if fingerprint(path) != original:
            raise ValueError(f"Document changed during analysis: {path.name}; run again")
        item = plan_item(path, output, classification, original, reserved)
        plan.append(item)
        reserved.add(item.destination)
    table = Table(title="Proposed organization", show_lines=True)
    for heading in ("File", "Category", "Destination", "Reason"):
        table.add_column(heading)
    for item in plan:
        table.add_row(Text(item.source.name), item.classification.category.value,
                      Text(str(item.destination)), Text(item.classification.reason))
    console.print(table)
    if args.dry_run:
        console.print("Dry run complete. No files or directories were changed.", style="green")
        return 0
    try:
        confirmed = Confirm.ask(f"Move these {len(plan)} files?", default=False, console=console)
    except EOFError:
        confirmed = False
    if not confirmed:
        console.print("Cancelled. No files were moved.")
        return 0
    successes = 0
    for item in track(plan, description="Organizing", console=console):
        try:
            destination = move_file(item, source, output, confirmed=True)
        except (OSError, ValueError) as exc:
            logger.error("Move failed for %s (%s)", item.source.name, type(exc).__name__)
            console.print(Text(f"Failed {item.source.name}: {exc}", style="red"))
        else:
            successes += 1
            console.print(Text(f"✓ {item.source.name} → {destination}", style="green"))
    failures = len(plan) - successes
    console.print(f"Successfully organized {successes} files. Failed: {failures}.")
    return 1 if failures else 0


def main(argv: list[str] | None = None, *, console: Console | None = None) -> int:
    args = parser().parse_args(argv)
    console = console or Console()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        return run(args, console)
    except KeyboardInterrupt:
        console.print("Interrupted. Review completed moves and inspect output for partial copies before retrying.", style="yellow")
        return 130
    except (OSError, ValueError, ExtractionError, ClassificationError) as exc:
        console.print(Text(f"Error: {exc}", style="red"))
        return 1
