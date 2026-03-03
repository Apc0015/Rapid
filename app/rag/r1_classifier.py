"""
R1 — Document Classifier

Heuristic-based document type detection for uploaded files.
No LLM call needed. Determines optimal chunking and retrieval parameters.

Adapted from app/services/document_classifier.py with:
- Removed pipeline field (all uploads go through RAG)
- Added top_k_hint for type-specific retrieval
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any

logger = logging.getLogger(__name__)

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
]
_POLICY_KEYWORDS = [
    "policy", "procedure", "shall", "must not", "compliance",
    "guidelines", "regulation", "section", "clause", "article",
    "effective date", "scope", "purpose", "responsibilities",
]
_FINANCIAL_COL_KEYWORDS = [
    "revenue", "cost", "profit", "amount", "price", "salary",
    "balance", "budget", "tax", "total", "expense", "income",
]

_TEXT_EXTS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"}
_CODE_EXTS = {".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs",
              ".rb", ".php", ".sh", ".sql", ".ipynb"}
_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}

# top-K hints per doc type
_TOP_K_HINTS = {
    "academic": 7,
    "legal": 5,
    "financial_doc": 6,
    "medical": 6,
    "code": 5,
    "narrative": 4,
    "tabular": 4,
    "default": 4,
}


@dataclass
class ClassificationResult:
    doc_type: str          # narrative | academic | financial_doc | legal | medical | code | tabular
    doc_subtype: str       # policy | contract | research_paper | general | etc.
    confidence: float
    top_k_hint: int        # recommended top-K for retrieval
    stats: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class DocumentClassifier:
    """
    R1 — heuristic document type detection.
    All uploads go through the RAG pipeline regardless of type.
    """

    def classify(self, file_path: str, filename: str) -> ClassificationResult:
        ext = os.path.splitext(filename.lower())[1]
        try:
            if ext in (".csv", ".parquet"):
                return self._classify_tabular(file_path, filename, ext)
            if ext in (".xlsx", ".xls"):
                return self._classify_tabular(file_path, filename, ext)
            if ext in _TEXT_EXTS:
                return self._classify_text(file_path, filename, ext)
            if ext == ".json":
                return self._classify_json(file_path, filename)
            if ext in _CONFIG_EXTS:
                return self._make_result("narrative", "structured_data", 0.85, filename, ext)
            if ext in _CODE_EXTS:
                return self._make_result("code", "source_code", 0.92, filename, ext)
        except Exception as e:
            logger.warning("Classification failed for %s: %s", filename, e)

        return ClassificationResult(
            doc_type="narrative", doc_subtype="general",
            confidence=0.50, top_k_hint=4,
            reason=f"Could not classify {filename}; defaulting to narrative.",
        )

    def _classify_tabular(self, file_path: str, filename: str, ext: str) -> ClassificationResult:
        stats: Dict[str, Any] = {}
        try:
            import pandas as pd
            if ext in (".xlsx", ".xls"):
                xf = pd.ExcelFile(file_path)
                df = xf.parse(xf.sheet_names[0], nrows=5)
                stats = {"sheets": len(xf.sheet_names), "cols": len(df.columns)}
            elif ext == ".parquet":
                import pyarrow.parquet as pq
                pf = pq.read_metadata(file_path)
                stats = {"rows": pf.num_rows, "cols": pf.num_columns}
            else:
                df = pd.read_csv(file_path, nrows=5, low_memory=False)
                stats = {"cols": len(df.columns), "columns": list(df.columns)}
        except Exception as e:
            logger.debug("Could not read tabular stats for %s: %s", filename, e)

        return ClassificationResult(
            doc_type="tabular", doc_subtype="general_tabular",
            confidence=0.90, top_k_hint=_TOP_K_HINTS["tabular"],
            stats=stats,
            reason=f"Tabular file ({ext.upper().lstrip('.')})",
        )

    def _classify_text(self, file_path: str, filename: str, ext: str) -> ClassificationResult:
        text_sample = self._sample_text(file_path, ext)
        word_count = len(text_sample.split())
        stats: Dict[str, Any] = {"word_count": word_count}

        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                stats["pages"] = len(reader.pages)
            except Exception:
                pass

        text_lower = text_sample.lower()
        academic = self._keyword_score(text_lower, _ACADEMIC_KEYWORDS)
        legal = self._keyword_score(text_lower, _LEGAL_KEYWORDS)
        medical = self._keyword_score(text_lower, _MEDICAL_KEYWORDS)
        policy = self._keyword_score(text_lower, _POLICY_KEYWORDS)
        financial = bool(
            re.search(r"[\$€£¥]\s*[\d,]+", text_sample)
            and re.search(r"\b(revenue|profit|earnings|fiscal|quarter)\b", text_lower)
        )

        best = max(academic, legal, medical, policy)
        if best >= 3:
            if academic >= 3:
                return ClassificationResult("academic", "research_paper", 0.82, _TOP_K_HINTS["academic"], stats, "Academic text detected")
            if legal >= 3:
                return ClassificationResult("legal", "contract", 0.80, _TOP_K_HINTS["legal"], stats, "Legal language detected")
            if medical >= 3:
                return ClassificationResult("medical", "clinical_document", 0.78, _TOP_K_HINTS["medical"], stats, "Medical terminology detected")
            return ClassificationResult("narrative", "policy", 0.76, 4, stats, "Policy language detected")
        if financial:
            return ClassificationResult("financial_doc", "annual_report", 0.78, _TOP_K_HINTS["financial_doc"], stats, "Financial narrative detected")

        return ClassificationResult(
            doc_type="narrative", doc_subtype="general",
            confidence=0.65, top_k_hint=_TOP_K_HINTS["narrative"],
            stats=stats, reason=f"Text document ({word_count} words)",
        )

    def _classify_json(self, file_path: str, filename: str) -> ClassificationResult:
        try:
            import json
            with open(file_path, errors="ignore") as f:
                data = json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                sample = data[0]
                if all(not isinstance(v, (dict, list)) for v in sample.values()):
                    return ClassificationResult(
                        "tabular", "json_table", 0.85, _TOP_K_HINTS["tabular"],
                        {"rows": len(data), "cols": len(sample)}, "Flat JSON array",
                    )
        except Exception:
            pass
        return ClassificationResult("narrative", "structured_data", 0.65, 4, {}, "Nested JSON")

    @staticmethod
    def _make_result(doc_type, doc_subtype, confidence, filename, ext) -> ClassificationResult:
        return ClassificationResult(
            doc_type=doc_type, doc_subtype=doc_subtype,
            confidence=confidence, top_k_hint=_TOP_K_HINTS.get(doc_type, 4),
            reason=f"{doc_type} file ({ext})",
        )

    def _sample_text(self, file_path: str, ext: str, max_words: int = 2000) -> str:
        try:
            if ext == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(file_path)
                text = " ".join(
                    page.extract_text() or "" for page in reader.pages[:8]
                )
            elif ext == ".docx":
                import docx
                doc = docx.Document(file_path)
                text = " ".join(p.text for p in doc.paragraphs[:100])
            elif ext in (".html", ".htm"):
                from bs4 import BeautifulSoup
                with open(file_path, errors="ignore") as f:
                    text = BeautifulSoup(f.read(), "html.parser").get_text(" ")
            else:
                with open(file_path, errors="ignore") as f:
                    text = f.read(50_000)
        except Exception as e:
            logger.debug("Text sampling failed for %s: %s", file_path, e)
            return ""
        return " ".join(text.split()[:max_words])

    @staticmethod
    def _keyword_score(text_lower: str, keywords: list) -> int:
        return sum(1 for kw in keywords if kw in text_lower)
