"""
Text Extractor — extract plain text from various file formats.

Used during document upload to prepare text for chunking and indexing.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extracts text from PDF, DOCX, TXT, MD, HTML, CSV, JSON, and code files."""

    def extract(self, file_path: str, filename: str) -> str:
        """
        Extract text from a file. Returns plain text string.
        Falls back to empty string on extraction failure.
        """
        ext = os.path.splitext(filename.lower())[1]
        try:
            if ext == ".pdf":
                return self._extract_pdf(file_path)
            if ext == ".docx":
                return self._extract_docx(file_path)
            if ext in (".xlsx", ".xls"):
                return self._extract_excel(file_path)
            if ext == ".csv":
                return self._extract_csv(file_path)
            if ext in (".html", ".htm"):
                return self._extract_html(file_path)
            if ext == ".ipynb":
                return self._extract_notebook(file_path)
            # Plain text formats
            return self._extract_text(file_path)
        except Exception as e:
            logger.warning("Text extraction failed for %s: %s", filename, e)
            return ""

    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
        return "\n\n".join(pages)

    @staticmethod
    def _extract_docx(file_path: str) -> str:
        import docx
        doc = docx.Document(file_path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    @staticmethod
    def _extract_excel(file_path: str) -> str:
        import pandas as pd
        xf = pd.ExcelFile(file_path)
        parts = []
        for sheet in xf.sheet_names[:5]:
            df = xf.parse(sheet)
            parts.append(f"Sheet: {sheet}\n{df.to_string(index=False)}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_csv(file_path: str) -> str:
        import pandas as pd
        df = pd.read_csv(file_path, low_memory=False)
        return df.to_string(index=False)

    @staticmethod
    def _extract_html(file_path: str) -> str:
        from bs4 import BeautifulSoup
        with open(file_path, errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        return soup.get_text(separator="\n")

    @staticmethod
    def _extract_notebook(file_path: str) -> str:
        import json
        with open(file_path, errors="ignore") as f:
            nb = json.load(f)
        parts = []
        for cell in nb.get("cells", []):
            source = "".join(cell.get("source", []))
            if source.strip():
                cell_type = cell.get("cell_type", "code")
                parts.append(f"[{cell_type}]\n{source}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_text(file_path: str) -> str:
        with open(file_path, errors="ignore") as f:
            return f.read()
