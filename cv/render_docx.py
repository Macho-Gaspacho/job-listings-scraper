"""DOCX output, and PDF when LibreOffice is already installed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.shared import Inches, Mm

from cv.render_text import document_blocks


def render_docx(document, path: str | Path) -> Path:
    word = Document()
    section = word.sections[0]
    if document.preset.page_size == "letter":
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
    else:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
    for kind, text in document_blocks(document):
        if kind == "image":
            word.add_picture(text, width=Mm(30))
        elif kind == "h1":
            word.add_heading(text, level=1)
        elif kind == "h2":
            word.add_heading(text, level=2)
        elif kind == "h3":
            word.add_heading(text, level=3)
        elif kind == "bullet":
            try:
                word.add_paragraph(text, style="List Bullet")
            except KeyError:
                word.add_paragraph(text)
        else:
            word.add_paragraph(text)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    word.save(destination)
    return destination


def libreoffice_pdf(docx_path: str | Path) -> Path | None:
    """Convert with a local LibreOffice. Returns None when it is not installed."""
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        return None
    source = Path(docx_path)
    if not source.is_file():
        return None
    completed = subprocess.run(
        [
            binary,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(source.parent),
            str(source),
        ],
        check=False,
        capture_output=True,
    )
    pdf = source.with_suffix(".pdf")
    if completed.returncode != 0 or not pdf.is_file():
        return None
    return pdf
