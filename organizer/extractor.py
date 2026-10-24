"""Bounded text extraction; documents are never executed."""
from dataclasses import dataclass
from pathlib import Path
import os
import stat
from zipfile import BadZipFile

import pymupdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError

from organizer.file_manager import open_directory

from organizer.scanner import safe_path


class ExtractionError(Exception):
    """A supported document could not be read."""


@dataclass(frozen=True)
class ExtractedText:
    text: str
    warning: str | None = None


def extract_text(path: Path, max_chars: int = 6000) -> ExtractedText:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    path = safe_path(path)
    if path.suffix.lower() not in {".txt", ".pdf", ".docx"}:
        raise ExtractionError("Unsupported document format")
    # O_NOFOLLOW closes the final-component symlink race on supported platforms.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        with open_directory(path.parent) as directory_fd, os.fdopen(
            os.open(path.name, flags, dir_fd=directory_fd), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ExtractionError("Source is not a regular file")
            suffix = path.suffix.lower()
            if suffix == ".txt":
                raw = stream.read(max_chars * 4 + 3)
                text = raw.decode("utf-8-sig", errors="replace")[:max_chars]
                warning = "Invalid UTF-8 bytes were replaced." if "\ufffd" in text else None
                return ExtractedText(text, warning)
            if suffix == ".pdf":
                # PyMuPDF requires a path or bytes; a verified descriptor supplies bytes.
                with pymupdf.open(stream=stream.read(), filetype="pdf") as document:
                    if document.needs_pass:
                        raise ExtractionError("Password-protected PDF cannot be read")
                    chunks, length = [], 0
                    for page in document:
                        chunk = page.get_text()[:max_chars - length]
                        chunks.append(chunk)
                        length += len(chunk)
                        if length >= max_chars:
                            break
                    text = "".join(chunks)
            else:
                document = Document(stream)
                chunks, length = [], 0
                for block in document.iter_inner_content():
                    if hasattr(block, "text"):
                        chunk = block.text
                    else:
                        chunk = "\n".join(" | ".join(cell.text for cell in row.cells)
                                          for row in block.rows)
                    chunk = (chunk + "\n")[:max_chars - length]
                    chunks.append(chunk)
                    length += len(chunk)
                    if length >= max_chars:
                        break
                text = "".join(chunks)
    except (OSError, ValueError, BadZipFile, PackageNotFoundError, RuntimeError, XMLSyntaxError, KeyError) as exc:
        raise ExtractionError(f"Cannot extract {path.name}: {type(exc).__name__}") from exc
    if not text.strip():
        return ExtractedText("", "No extractable text; using filename only (no OCR).")
    return ExtractedText(text)
