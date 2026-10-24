"""Optional live smoke check: uses only generated temporary documents.

Run with the project virtualenv and a local qwen2.5:7b model available.
"""
import hashlib
import sys
from pathlib import Path
import subprocess
import tempfile
import pymupdf
from docx import Document

project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='organizer-live-') as temporary:
    root = Path(temporary).resolve()
    (root / 'lecture.txt').write_text('University lecture notes. Introduction to calculus: derivatives, integrals, and homework exercises.')
    (root / 'resume.txt').write_text('Resume. Alex Example. Software developer. Work experience: Python programmer. Skills: Python, SQL. Education: BSc Computer Science.')
    (root / 'recipe.txt').write_text('Pancake recipe: mix flour, eggs and milk. Fry in a pan and serve with honey.')
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Invoice #123. Consulting services. Total amount due: USD 500. Payment due in 30 days.')
        pdf.save(root / 'invoice.pdf')
    doc = Document()
    doc.add_paragraph('Service Agreement. This legally binding contract is between Company A and Company B. Both parties agree to confidentiality and termination clauses.')
    doc.save(root / 'contract.docx')
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    command = [sys.executable, 'main.py', str(root)]
    dry = subprocess.run(command + ['--dry-run'], cwd=project, text=True, capture_output=True, timeout=600)
    print('DRY RUN', dry.returncode, dry.stdout, dry.stderr, flush=True)
    assert dry.returncode == 0
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    moved = subprocess.run(command, cwd=project, input='y\n', text=True, capture_output=True, timeout=600)
    print('CONFIRMED RUN', moved.returncode, moved.stdout, moved.stderr, flush=True)
    assert moved.returncode == 0
    expected = {'lecture.txt': 'Education', 'resume.txt': 'Career', 'invoice.pdf': 'Finance', 'contract.docx': 'Legal', 'recipe.txt': 'Other'}
    for name, category in expected.items():
        destination = root / category / name
        assert destination.exists(), str(destination)
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == before[name]
        assert not (root / name).exists()
    print('PASS: 5 live classifications, dry-run unchanged, 5 confirmed moves, all SHA-256 hashes intact.', flush=True)
