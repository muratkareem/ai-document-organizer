# AI Document Organizer

A local command-line application that reads PDF, DOCX, and TXT documents, asks
Ollama to classify them, and shows a proposed folder layout before moving anything.
It helps sort a mixed download folder while keeping the decision visible to you.

Documents are classified into **Education**, **Career**, **Finance**, **Legal**, or
**Other**. The model provides a short reason for each suggestion. Review the plan:
classification is a suggestion and can be wrong.

## Features

- Non-recursive scanning with explanations for skipped files.
- Text extraction from PDFs, DOCX paragraphs and tables, and UTF-8 text files.
- Local Ollama inference with a configurable model and bounded text input.
- JSON schema output validated by Pydantic, with bounded retries and useful errors.
- Rich progress indicators and a table showing filenames, categories, destinations,
  and classification reasons.
- Dry-run mode, default-no confirmation, collision suffixes, and source change checks.
- Separate output directories, including directories that do not yet exist.

## Stack

Python 3.11+ and `pathlib` provide the application and filesystem interface.
PyMuPDF extracts PDF text; python-docx reads Word documents. Pydantic v2 validates
classification results, Rich renders the CLI, and pytest tests the workflows.
Ollama runs the language model locally. The application uses Python's standard
HTTP client and logging; it requires no cloud account or paid API.

## Installation

On macOS, install Python 3.11 or newer (for example, `brew install python`) and Git.
Then:

```bash
git clone https://github.com/muratkareem/ai-document-organizer.git
cd ai-document-organizer

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Install [Ollama for macOS](https://ollama.com/download/mac) and open the app, or
install the CLI with `brew install ollama` and run `ollama serve` in another terminal.
Use one running server; an address-in-use message usually means it is already running.

Download a model and check it is available:

```bash
ollama pull qwen2.5:7b
ollama list
```

The example model requires several gigabytes of disk space and enough available
memory to run. You may choose another installed text model with `--model`; no
particular model is required by the application. The first inference may take
longer while Ollama loads the model.

Installation and model downloads require internet access. Afterward, organization
works offline. Requests go only to `127.0.0.1:11434`; HTTP proxy environment variables
are ignored. Full document contents are never logged by this application.

## Usage

Start with a preview:

```bash
python main.py --help
python main.py ~/Downloads --dry-run
python main.py ~/Downloads
python main.py ~/Downloads --model qwen2.5:7b
python main.py ~/Downloads --output ~/Documents/Organized
python main.py ~/Downloads --max-chars 4000 --timeout 180 --dry-run
```

`--max-chars` bounds the extracted text sent per document (default 6000).
`--timeout` sets seconds per request (default 120). Failed transient requests or
invalid responses are retried once. Files are analyzed sequentially. There is no
`--yes` bypass: a non-dry run always asks for confirmation, and EOF cancels.

The optional installed command is also available after `pip install -e .`:

```bash
ai-document-organizer ~/Downloads --dry-run
```

Example (paths and model reasons shortened here for readability):

```text
AI Document Organizer
Scanning: /Users/alex/Downloads
Found 4 supported documents.
Analyzing documents with Ollama...

Proposed organization
File             Category    Destination                      Reason
lecture.txt      Education   .../Education/lecture.txt        University notes
resume.pdf       Career      .../Career/resume.pdf            Work experience
invoice.pdf      Finance     .../Finance/invoice.pdf          Payment invoice
contract.docx    Legal       .../Legal/contract.docx          Service agreement

Move these 4 files? [y/n] (n): y
✓ lecture.txt → .../Education/lecture.txt
✓ resume.pdf → .../Career/resume.pdf
✓ invoice.pdf → .../Finance/invoice.pdf
✓ contract.docx → .../Legal/contract.docx
Successfully organized 4 files. Failed: 0.
```

Exit codes: `0` for success, empty scans, previews, or cancellation; `1` for an
operational failure (including partial movement); `2` for invalid CLI arguments;
`130` for interruption.

## How it works

Document scanning → Text extraction → Ollama classification → Pydantic validation
→ Plan preview → User confirmation → File organization.

The prompt treats filenames and document text as untrusted data and asks for Other
when evidence is insufficient. Ollama receives a
[JSON schema](https://docs.ollama.com/capabilities/structured-outputs); Pydantic
rejects unknown categories, extra fields, and empty or excessively long reasons.
Only predefined category names are mapped to directories. Model output never
becomes an arbitrary path or command.

## Safety and failure behavior

- Dry-run creates no output folders and does not move files. It still calls Ollama.
- Only regular supported files directly inside the selected source are considered.
  Existing category subdirectories are skipped on subsequent runs.
- Source, output, and category paths cannot contain symlink components or `..`.
  If a legitimate path uses a symlink, pass its real absolute directory instead.
- Existing destinations are preserved. The preview selects names such as
  `report_1.pdf` and reserves them across the whole plan.
- A destination created by another process after preview causes that move to fail;
  it is never overwritten and the application does not silently change the plan.
- File identity, size, and modification metadata are checked after analysis and
  before and during movement. Changed or missing sources are not moved.
- On macOS/Linux, directory descriptors and no-follow opens prevent symlink
  traversal during file operations. The destination is created exclusively,
  copied, flushed to disk, and checked before deleting the original. This also
  supports output on another filesystem.
- A corrupt/unreadable document or classification failure aborts analysis before
  confirmation; it does not silently classify everything as Other.
- Individual move failures are reported, and remaining approved moves are attempted.
  This is not an all-or-nothing batch transaction.
- A failed or interrupted copy can leave a partial destination beside the intact
  source. A failed source deletion leaves both copies. Inspect the reported path
  before retrying; incomplete destinations are deliberately not automatically deleted.

Keep backups and avoid editing files or renaming folders while organizing them.
Checks reduce concurrency risks, but this tool is not a security boundary against
another process deliberately modifying the same directories between system calls.
Reading may update access times. File contents, permission bits, and modification
times are preserved; extended attributes, ACLs, resource forks, and creation times
are not guaranteed to be preserved.

## Tests

```bash
python -m pytest -q
```

Tests generate documents in temporary directories and mock Ollama. They require
neither a running model nor personal files. Coverage includes scanning, PDF/DOCX/TXT
extraction, schema validation, service failures, dry-run, confirmation, collisions,
symlinks, changed sources, permission errors, and failed copies/deletions.

To repeat the optional live check (requires Ollama and `qwen2.5:7b`), run
`python scripts/live_smoke.py`. It makes ten inference requests and moves only
generated documents inside a temporary directory, which is removed afterward.

Development verification on macOS Apple Silicon with Python 3.14: **54 tests passed**.
A live `qwen2.5:7b` check used five generated documents spanning all categories and
all supported formats. Both dry-run and confirmed movement succeeded; SHA-256
checks verified unchanged contents. PyMuPDF emitted five upstream SWIG deprecation
warnings during pytest; there were no test failures.

## Troubleshooting

- **Cannot reach Ollama:** open the Ollama app or run `ollama serve`, then check
  `ollama list`. Increase `--timeout` if model loading takes too long.
- **Model unavailable:** run `ollama pull MODEL_NAME` and use the same `--model` value.
- **Invalid classification / rejected schema:** update Ollama or try another model.
- **Permission denied:** choose directories your account can read and write.
- **Source changed:** stop other edits and run a new preview.
- **No extractable PDF text:** filename-only classification is shown with a warning.
- **Encrypted or corrupt document:** remove it from the selected input folder or
  supply an accessible copy, then retry. The tool does not bypass PDF passwords.

## Project layout

```text
main.py                    Source-checkout entry point
organizer/
  scanner.py               Directory validation and discovery
  extractor.py             Text extraction
  models.py                Allowed categories and response schema
  classifier.py            Local Ollama requests and retries
  file_manager.py           Planning and protected file operations
  cli.py                   Arguments, preview, confirmation, summary
tests/                     Generated fixtures and mocked workflows
requirements.txt           Runtime and test dependencies
pyproject.toml             Package metadata and pytest configuration
```

## Limitations

- No OCR: scanned PDFs fall back to filename-only classification when no text exists.
- Only PDF, DOCX, and TXT are supported; no recursive scanning.
- Classification quality depends on the local model. A valid response can still be wrong.
- Text uses an initial excerpt, so important information later in a file may be missed.
- The prompt is bounded, but PDF/DOCX parsing can load the document into memory.
  Very large or hostile documents are not resource-sandboxed.
- No undo command, batch rollback, background watcher, or parallel inference.
- Safe movement targets macOS and Linux. On other platforms movement fails closed;
  scanning and previews are intended to work but have not been verified on Windows.
- Linux and Python 3.11–3.13 compatibility have not been exercised in this environment.

## License

MIT. See [LICENSE](LICENSE).
