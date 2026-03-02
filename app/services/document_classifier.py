"""
Document Type Classifier for Intelligent Auto-RAG.

Classifies uploaded documents by content type so the system can
automatically choose the optimal processing pipeline (SQL vs RAG)
and retrieval configuration for each document.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Keywords used for text-based subtype detection
_ACADEMIC_KEYWORDS = [
    "abstract", "introduction", "methodology", "conclusion",
    "references", "doi", "hypothesis", "experiment", "findings",
    "literature review", "related work", "citation",
]
_LEGAL_KEYWORDS = [
    "whereas", "hereinafter", "pursuant", "indemnification",
    "liability", "agreement", "party", "parties", "notwithstanding",
    "arbitration", "jurisdiction", "governing law", "covenant",
]
_MEDICAL_KEYWORDS = [
    "patient", "diagnosis", "treatment", "medication", "clinical",
    "icd", "symptom", "prognosis", "therapy", "dosage", "prescription",
    "disease", "syndrome", "pathology", "etiology",
]
_POLICY_KEYWORDS = [
    "policy", "procedure", "shall", "must not", "compliance",
    "guidelines", "regulation", "section", "clause", "article",
    "effective date", "scope", "purpose", "responsibilities",
]
_FINANCIAL_COL_KEYWORDS = [
    "revenue", "cost", "profit", "amount", "price", "salary",
    "balance", "budget", "tax", "total", "expense", "income",
    "loss", "earning", "margin", "rate", "payment", "invoice",
]

# Extensions that are always tabular (no ambiguity)
_ALWAYS_TABULAR_EXTS = {".csv", ".parquet"}
# Extensions that are usually tabular
_LIKELY_TABULAR_EXTS = {".xlsx", ".xls"}
# Extensions that need content analysis
_TEXT_EXTS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"}
# Ambiguous — check content
_AMBIGUOUS_EXTS = {".json", ".xml"}
# Config / data files → treated as narrative/structured_data for RAG
_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
# Code files → treated as code type for RAG
_CODE_EXTS = {".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs",
              ".rb", ".php", ".sh", ".sql", ".ipynb"}


@dataclass
class ClassificationResult:
    """Result of document type classification."""
    doc_type: str          # tabular | narrative | academic | financial_doc | legal | medical | mixed
    doc_subtype: str       # financial_spreadsheet | policy | research_paper | hr_data | general | etc.
    pipeline: str          # sql | rag
    confidence: float      # 0.0 – 1.0
    stats: Dict[str, Any]  # rows, cols, word_count, sheets, pages, columns, etc.
    reason: str            # Human-readable explanation


class DocumentClassifier:
    """
    Classifies uploaded documents by content type.

    Uses heuristics (file extension + content sampling) —
    no LLM call needed for classification.
    """

    def classify(self, file_path: str, filename: str) -> ClassificationResult:
        """
        Classify a document and return a ClassificationResult.

        Args:
            file_path: Absolute path to the saved file.
            filename: Original filename (used for extension detection).

        Returns:
            ClassificationResult with type, subtype, pipeline, confidence, stats, reason.
        """
        ext = os.path.splitext(filename.lower())[1]

        try:
            if ext in _ALWAYS_TABULAR_EXTS:
                return self._classify_tabular(file_path, filename, ext, base_confidence=0.95)

            if ext in _LIKELY_TABULAR_EXTS:
                return self._classify_tabular(file_path, filename, ext, base_confidence=0.92)

            if ext in _TEXT_EXTS:
                return self._classify_text(file_path, filename, ext)

            if ext == ".json":
                return self._classify_json(file_path, filename)

            if ext == ".xml":
                return self._classify_xml(file_path, filename)

            if ext in _CONFIG_EXTS:
                return self._classify_config(file_path, filename, ext)

            if ext in _CODE_EXTS:
                return self._classify_code(file_path, filename, ext)

        except Exception as e:
            logger.warning("Classification failed for %s: %s — defaulting to narrative/rag", filename, e)

        # Safe fallback
        return ClassificationResult(
            doc_type="narrative",
            doc_subtype="general",
            pipeline="rag",
            confidence=0.50,
            stats={"note": "classification fallback"},
            reason=f"Could not classify {filename}; defaulting to RAG pipeline.",
        )

    # ─── Tabular ──────────────────────────────────────────────────────────────

    def _classify_tabular(self, file_path: str, filename: str, ext: str,
                          base_confidence: float) -> ClassificationResult:
        import pandas as pd

        stats: Dict[str, Any] = {}
        subtype = "general_tabular"
        confidence = base_confidence

        try:
            if ext in (".xlsx", ".xls"):
                xf = pd.ExcelFile(file_path)
                sheets = xf.sheet_names
                stats["sheets"] = sheets
                stats["sheet_count"] = len(sheets)
                # Read first sheet for shape
                df = xf.parse(sheets[0], nrows=5)
                total_rows = sum(
                    len(xf.parse(s)) for s in sheets[:5]  # cap at 5 sheets
                )
                stats["rows"] = total_rows
                stats["cols"] = len(df.columns)
                stats["columns"] = list(df.columns)
            elif ext == ".parquet":
                import pyarrow.parquet as pq
                pf = pq.read_metadata(file_path)
                stats["rows"] = pf.num_rows
                stats["cols"] = pf.num_columns
                stats["columns"] = [
                    pf.row_group(0).column(i).path_in_schema
                    for i in range(min(pf.num_columns, 20))
                ]
            else:  # csv
                df = pd.read_csv(file_path, nrows=5, low_memory=False)
                # Count total rows efficiently
                with open(file_path, "r", errors="ignore") as f:
                    total_rows = sum(1 for _ in f) - 1  # subtract header
                stats["rows"] = max(total_rows, 0)
                stats["cols"] = len(df.columns)
                stats["columns"] = list(df.columns)

            # Detect financial subtype from column names
            col_names_lower = " ".join(str(c).lower() for c in stats.get("columns", []))
            financial_hits = sum(
                1 for kw in _FINANCIAL_COL_KEYWORDS if kw in col_names_lower
            )
            if financial_hits >= 2:
                subtype = "financial_spreadsheet"
                confidence = min(base_confidence + 0.02, 0.99)
            elif any(kw in col_names_lower for kw in ["employee", "staff", "hire", "department", "salary"]):
                subtype = "hr_data"
            elif any(kw in col_names_lower for kw in ["product", "sku", "inventory", "stock", "quantity"]):
                subtype = "inventory"
            else:
                subtype = "general_tabular"

            reason = (
                f"{ext.upper().lstrip('.')} file with "
                f"{stats.get('rows', '?')} rows and {stats.get('cols', '?')} columns"
            )
            if stats.get("sheet_count", 0) > 1:
                reason += f" across {stats['sheet_count']} sheets"

        except Exception as e:
            logger.warning("Could not load tabular file %s: %s", filename, e)
            stats = {"error": str(e)}
            reason = f"Tabular file ({ext}) — could not read shape"
            confidence = max(base_confidence - 0.10, 0.50)

        return ClassificationResult(
            doc_type="tabular",
            doc_subtype=subtype,
            pipeline="sql",
            confidence=confidence,
            stats=stats,
            reason=reason,
        )

    # ─── Text / Narrative ─────────────────────────────────────────────────────

    def _classify_text(self, file_path: str, filename: str, ext: str) -> ClassificationResult:
        text_sample = self._sample_text(file_path, ext, max_words=2000)
        word_count = len(text_sample.split())
        stats: Dict[str, Any] = {"word_count": word_count}

        # Markdown with tables → table_intact chunking strategy
        if ext in (".md", ".markdown"):
            table_rows = [
                line for line in text_sample.splitlines()
                if re.match(r"^\s*\|.*\|", line)
            ]
            if len(table_rows) >= 3:
                return ClassificationResult(
                    doc_type="narrative",
                    doc_subtype="markdown_table",
                    pipeline="rag",
                    confidence=0.80,
                    stats={"word_count": word_count, "table_rows": len(table_rows)},
                    reason=f"Markdown file with {len(table_rows)} table rows detected — using table_intact chunking",
                )

        # Try to get page count for PDFs
        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                stats["pages"] = len(reader.pages)
            except Exception:
                pass

        text_lower = text_sample.lower()

        # Score each category
        academic_score = self._keyword_score(text_lower, _ACADEMIC_KEYWORDS)
        legal_score = self._keyword_score(text_lower, _LEGAL_KEYWORDS)
        medical_score = self._keyword_score(text_lower, _MEDICAL_KEYWORDS)
        policy_score = self._keyword_score(text_lower, _POLICY_KEYWORDS)

        # Financial narrative (PDF with numbers/currency, not a spreadsheet)
        financial_narrative = bool(
            re.search(r"[\$€£¥]\s*[\d,]+", text_sample) and
            re.search(r"\b(revenue|profit|earnings|fiscal|quarter|annual report)\b", text_lower)
        )

        scores = {
            "academic": academic_score,
            "legal": legal_score,
            "medical": medical_score,
            "narrative_policy": policy_score,
        }
        top_category = max(scores, key=scores.get)
        top_score = scores[top_category]

        if top_score >= 3 or financial_narrative:
            if financial_narrative and top_score < 3:
                doc_type, subtype, confidence = "financial_doc", "annual_report", 0.78
                reason = "PDF with financial figures and narrative text"
            elif top_category == "academic" and top_score >= 3:
                doc_type, subtype, confidence = "academic", "research_paper", 0.82
                reason = f"Academic text (matched: abstract/intro/references keywords)"
            elif top_category == "legal" and top_score >= 3:
                doc_type, subtype, confidence = "legal", "contract", 0.80
                reason = "Legal language detected (whereas, pursuant, indemnification, etc.)"
            elif top_category == "medical" and top_score >= 3:
                doc_type, subtype, confidence = "medical", "clinical_document", 0.78
                reason = "Medical/clinical terminology detected"
            else:  # policy
                doc_type, subtype, confidence = "narrative", "policy", 0.76
                reason = "Policy/procedure language detected"
        else:
            # No strong signal — generic narrative
            doc_type = "narrative"
            subtype = "general"
            confidence = 0.65
            reason = f"Text document with no strong domain signal ({word_count} words)"

        return ClassificationResult(
            doc_type=doc_type,
            doc_subtype=subtype,
            pipeline="rag",
            confidence=confidence,
            stats=stats,
            reason=reason,
        )

    # ─── JSON ─────────────────────────────────────────────────────────────────

    def _classify_json(self, file_path: str, filename: str) -> ClassificationResult:
        import json

        try:
            with open(file_path, "r", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            return ClassificationResult(
                doc_type="narrative", doc_subtype="general",
                pipeline="rag", confidence=0.55,
                stats={}, reason="JSON file (could not parse)",
            )

        # Array of flat dicts → tabular
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            # Check if values are all scalars (flat table)
            sample = data[0]
            is_flat = all(not isinstance(v, (dict, list)) for v in sample.values())
            if is_flat:
                cols = list(sample.keys())
                col_names_lower = " ".join(c.lower() for c in cols)
                financial_hits = sum(1 for kw in _FINANCIAL_COL_KEYWORDS if kw in col_names_lower)
                subtype = "financial_spreadsheet" if financial_hits >= 2 else "general_tabular"
                return ClassificationResult(
                    doc_type="tabular", doc_subtype=subtype,
                    pipeline="sql", confidence=0.85,
                    stats={"rows": len(data), "cols": len(cols), "columns": cols},
                    reason=f"JSON array of {len(data)} flat objects — treating as tabular",
                )

        # Nested JSON → narrative/structured
        return ClassificationResult(
            doc_type="narrative", doc_subtype="structured_data",
            pipeline="rag", confidence=0.65,
            stats={"type": type(data).__name__},
            reason="Nested JSON structure — using RAG pipeline",
        )

    # ─── XML ──────────────────────────────────────────────────────────────────

    def _classify_xml(self, file_path: str, filename: str) -> ClassificationResult:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Check if it looks like a row-based table (same repeated child tags)
            children = list(root)
            if len(children) > 2:
                child_tags = [c.tag for c in children[:20]]
                if len(set(child_tags)) == 1:
                    # All children have same tag → row-based table
                    sample_child = children[0]
                    cols = [sub.tag for sub in sample_child]
                    return ClassificationResult(
                        doc_type="tabular", doc_subtype="general_tabular",
                        pipeline="sql", confidence=0.75,
                        stats={"rows": len(children), "cols": len(cols), "columns": cols},
                        reason=f"XML with repeated <{child_tags[0]}> rows — treating as tabular",
                    )
        except Exception:
            pass

        return ClassificationResult(
            doc_type="narrative", doc_subtype="structured_data",
            pipeline="rag", confidence=0.60,
            stats={}, reason="XML document — using RAG pipeline",
        )

    # ─── Config files ─────────────────────────────────────────────────────────

    def _classify_config(self, file_path: str, filename: str, ext: str) -> ClassificationResult:
        """YAML / TOML / INI / CFG / CONF → narrative/structured_data."""
        try:
            size = os.path.getsize(file_path)
        except Exception:
            size = 0
        return ClassificationResult(
            doc_type="narrative",
            doc_subtype="structured_data",
            pipeline="rag",
            confidence=0.85,
            stats={"size_bytes": size, "format": ext.lstrip(".")},
            reason=f"Configuration file ({ext}) — RAG pipeline on structured text",
        )

    # ─── Code files ───────────────────────────────────────────────────────────

    def _classify_code(self, file_path: str, filename: str, ext: str) -> ClassificationResult:
        """Source code / notebooks → code type for RAG."""
        try:
            with open(file_path, "r", errors="ignore") as f:
                content = f.read()
            line_count = content.count("\n") + 1
        except Exception:
            content = ""
            line_count = 0

        subtype = "notebook" if ext == ".ipynb" else "source_code"
        return ClassificationResult(
            doc_type="code",
            doc_subtype=subtype,
            pipeline="rag",
            confidence=0.92,
            stats={"lines": line_count, "language": ext.lstrip(".")},
            reason=f"Source code file ({ext}) — {line_count} lines, RAG pipeline",
        )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _sample_text(self, file_path: str, ext: str, max_words: int = 2000) -> str:
        """Extract a text sample from a file for keyword analysis."""
        try:
            if ext == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(file_path)
                pages_text = []
                for page in reader.pages[:8]:  # first 8 pages
                    pages_text.append(page.extract_text() or "")
                text = " ".join(pages_text)
            elif ext == ".docx":
                import docx
                doc = docx.Document(file_path)
                text = " ".join(p.text for p in doc.paragraphs[:100])
            elif ext in (".html", ".htm"):
                from bs4 import BeautifulSoup
                with open(file_path, "r", errors="ignore") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")
                text = soup.get_text(separator=" ")
            else:
                with open(file_path, "r", errors="ignore") as f:
                    text = f.read(50_000)  # first 50KB
        except Exception as e:
            logger.debug("Text sampling failed for %s: %s", file_path, e)
            return ""

        words = text.split()
        return " ".join(words[:max_words])

    @staticmethod
    def _keyword_score(text_lower: str, keywords: list) -> int:
        """Count how many keywords from the list appear in text_lower."""
        return sum(1 for kw in keywords if kw in text_lower)
