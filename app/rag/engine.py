import os
import re
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from pypdf import PdfReader
from docx import Document

from app.services.llm_service import LLMManager
from app.services.embedding_service import EmbeddingManager

logger = logging.getLogger(__name__)


def _get_chromadb():
    """Lazy-import chromadb to avoid numpy crash at module-load time."""
    import app.compat  # noqa: F401  — numpy 2.0 shim
    import chromadb
    return chromadb


def _extract_document_date(text: str) -> Optional[str]:
    """
    Extract the most prominent date from a document for version awareness.

    Looks for patterns like:
      - "Effective Date: January 1, 2024"
      - "Published: 2023-06-15"
      - "Version 2.1 — March 2024"
      - ISO 8601: 2024-01-15
      - US format: 01/15/2024

    Returns an ISO date string "YYYY-MM-DD" or None.
    """
    import re as _re

    # Check first 3000 chars for date signals (headers/titles carry dates)
    sample = text[:3000]

    # ISO date
    iso = _re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", sample)
    if iso:
        y, m, d = iso.groups()
        if 1980 <= int(y) <= 2035 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{m}-{d}"

    # US date: MM/DD/YYYY
    us = _re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", sample)
    if us:
        m, d, y = us.groups()
        if 1980 <= int(y) <= 2035:
            return f"{y}-{int(m):02d}-{int(d):02d}"

    # Month name + year (common in docs): "January 2024", "Jan. 2024"
    months = {
        "january": "01", "jan": "01", "february": "02", "feb": "02",
        "march": "03", "mar": "03", "april": "04", "apr": "04",
        "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
        "august": "08", "aug": "08", "september": "09", "sep": "09",
        "october": "10", "oct": "10", "november": "11", "nov": "11",
        "december": "12", "dec": "12",
    }
    month_re = _re.compile(
        r"\b(" + "|".join(months.keys()) + r")\.?\s+(\d{4})\b",
        _re.IGNORECASE,
    )
    m_match = month_re.search(sample)
    if m_match:
        mon, yr = m_match.groups()
        if 1980 <= int(yr) <= 2035:
            return f"{yr}-{months[mon.lower().rstrip('.')]}-01"

    return None


def _apply_recency_boost(results: List[Dict], boost_weight: float = 0.05) -> List[Dict]:
    """
    Apply a small recency boost to search results based on doc_date metadata.

    More recent documents get a slight score improvement. The boost is small
    (max 5% of score) to avoid overriding relevance.

    Args:
        results: List of search result dicts with optional metadata.doc_date.
        boost_weight: Maximum boost fraction (0.05 = 5%).

    Returns:
        Re-ranked results list.
    """
    if not results:
        return results

    import re as _re
    from datetime import datetime as _dt

    now_year = _dt.now().year

    def _year_from_date(date_str: Optional[str]) -> Optional[int]:
        if not date_str:
            return None
        m = _re.search(r"(\d{4})", str(date_str))
        return int(m.group(1)) if m else None

    # Compute boosted scores
    boosted = []
    for r in results:
        score = r.get("score", 0.5)
        doc_year = _year_from_date(r.get("metadata", {}).get("doc_date"))
        if doc_year:
            age = max(0, now_year - doc_year)
            # Newer = higher boost; decay over 10 years
            recency = max(0.0, 1.0 - age / 10.0)
            score = score * (1.0 - boost_weight) + recency * boost_weight
        boosted.append({**r, "score": score})

    # Re-sort by boosted score (ascending distance in ChromaDB, so sort ascending)
    return sorted(boosted, key=lambda x: x.get("score", 0.5))


class TextExtractor:
    @staticmethod
    def extract_text(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        extractors = {
            '.pdf': TextExtractor._extract_pdf,
            '.docx': TextExtractor._extract_docx,
            '.txt': TextExtractor._extract_txt,
            '.csv': TextExtractor._extract_csv,
            '.json': TextExtractor._extract_json,
            '.xlsx': TextExtractor._extract_excel,
            '.xls': TextExtractor._extract_excel,
            '.html': TextExtractor._extract_html,
            '.htm': TextExtractor._extract_html,
            '.md': TextExtractor._extract_markdown,
            '.markdown': TextExtractor._extract_markdown,
            '.xml': TextExtractor._extract_xml,
            '.parquet': TextExtractor._extract_parquet,
            # Config / data formats
            '.yaml': TextExtractor._extract_yaml,
            '.yml': TextExtractor._extract_yaml,
            '.toml': TextExtractor._extract_toml,
            '.ini': TextExtractor._extract_ini,
            '.cfg': TextExtractor._extract_ini,
            '.conf': TextExtractor._extract_ini,
            # Code files (read as-is with syntax header)
            '.py': TextExtractor._extract_code,
            '.js': TextExtractor._extract_code,
            '.ts': TextExtractor._extract_code,
            '.java': TextExtractor._extract_code,
            '.cpp': TextExtractor._extract_code,
            '.c': TextExtractor._extract_code,
            '.go': TextExtractor._extract_code,
            '.rs': TextExtractor._extract_code,
            '.rb': TextExtractor._extract_code,
            '.php': TextExtractor._extract_code,
            '.sh': TextExtractor._extract_code,
            '.sql': TextExtractor._extract_code,
            # Jupyter Notebooks
            '.ipynb': TextExtractor._extract_notebook,
        }
        extractor = extractors.get(ext)
        if extractor is None:
            raise ValueError(f"Unsupported file type: {ext}")
        return extractor(file_path)

    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    @staticmethod
    def _extract_txt(file_path: str) -> str:
        """Extract plain text files with proper resource management."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _extract_docx(file_path: str) -> str:
        doc = Document(file_path)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text

    @staticmethod
    def _extract_json(file_path: str) -> str:
        """Extract JSON files — flattens nested structures into readable text."""
        import json as json_mod

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json_mod.load(f)

        def _flatten(obj, prefix=""):
            lines = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}.{k}" if prefix else k
                    lines.extend(_flatten(v, key))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    lines.extend(_flatten(item, f"{prefix}[{i}]"))
            else:
                lines.append(f"{prefix}: {obj}")
            return lines

        if isinstance(data, list):
            text = f"JSON File: {os.path.basename(file_path)}\nRecords: {len(data)}\n\n"
            for i, record in enumerate(data):
                text += f"--- Record {i+1} ---\n"
                text += "\n".join(_flatten(record)) + "\n\n"
        else:
            text = f"JSON File: {os.path.basename(file_path)}\n\n"
            text += "\n".join(_flatten(data))
        return text

    @staticmethod
    def _extract_excel(file_path: str) -> str:
        """Extract Excel files (xlsx/xls) — reads all sheets."""
        import pandas as pd

        text = f"Excel File: {os.path.basename(file_path)}\n\n"
        xls = pd.ExcelFile(file_path)

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            text += f"--- Sheet: {sheet_name} ---\n"
            text += f"Columns: {', '.join(str(c) for c in df.columns)}\n"
            text += f"Rows: {len(df)}\n\n"
            text += df.to_string(index=False) + "\n\n"

        return text

    @staticmethod
    def _extract_html(file_path: str) -> str:
        """Extract text from HTML files using BeautifulSoup with regex fallback."""
        encoding = TextExtractor._detect_encoding(file_path)
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            raw_html = f.read()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw_html, 'html.parser')
            # Remove script and style elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            title = soup.title.string if soup.title else os.path.basename(file_path)
            text = f"HTML Document: {title}\n\n"
            text += soup.get_text(separator='\n', strip=True)
            return text
        except ImportError:
            logger.warning("BeautifulSoup (bs4) not installed — falling back to regex HTML extraction")
            # Regex fallback: strip tags and decode common entities
            title_match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else os.path.basename(file_path)
            # Remove script/style blocks
            text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            # Strip remaining tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Decode basic HTML entities
            for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                                  ('&nbsp;', ' '), ('&quot;', '"'), ('&#39;', "'")]:
                text = text.replace(entity, char)
            return f"HTML Document: {title}\n\n" + re.sub(r'\s{3,}', '\n\n', text).strip()

    @staticmethod
    def _extract_markdown(file_path: str) -> str:
        """Extract Markdown files — read as-is (markdown is already text)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"Markdown File: {os.path.basename(file_path)}\n\n{content}"

    @staticmethod
    def _extract_xml(file_path: str) -> str:
        """Extract XML files — flattens hierarchy into readable key-value text."""
        import xml.etree.ElementTree as ET

        def _strip_ns(tag: str) -> str:
            """Remove namespace URI, keep local name."""
            if "}" in tag:
                return tag.split("}", 1)[1]
            return tag

        def _flatten_element(elem, parent_key=""):
            lines = []
            tag = _strip_ns(elem.tag)
            key = f"{parent_key}.{tag}" if parent_key else tag

            # Attributes
            for attr_name, attr_val in elem.attrib.items():
                attr_name = _strip_ns(attr_name)
                lines.append(f"{key}.@{attr_name}: {attr_val}")

            # Text content
            text = (elem.text or "").strip()
            if text:
                lines.append(f"{key}: {text}")

            # Recurse into children
            child_counts: dict = {}
            for child in elem:
                child_tag = _strip_ns(child.tag)
                idx = child_counts.get(child_tag, 0)
                child_counts[child_tag] = idx + 1
                child_key = f"{key}.{child_tag}[{idx}]" if child_counts[child_tag] > 1 or len(list(elem.iter(child.tag))) > 1 else key
                lines.extend(_flatten_element(child, child_key if child_key != key else key))

            return lines

        tree = ET.parse(file_path)
        root = tree.getroot()

        text = f"XML File: {os.path.basename(file_path)}\n\n"
        text += "\n".join(_flatten_element(root))
        return text

    @staticmethod
    def _extract_parquet(file_path: str) -> str:
        """Extract Parquet files — reads columnar data into text."""
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise RuntimeError("pyarrow is required for Parquet support. Install with: pip install pyarrow")

        pf = pq.ParquetFile(file_path)
        metadata = pf.metadata
        num_rows = metadata.num_rows
        schema = pf.schema_arrow

        text = f"Parquet File: {os.path.basename(file_path)}\n"
        text += f"Rows: {num_rows}\n"
        text += f"Columns: {', '.join(schema.names)}\n\n"

        STREAM_THRESHOLD = 500_000  # rows

        if num_rows <= STREAM_THRESHOLD:
            table = pf.read()
            df = table.to_pandas()
            text += df.to_string(index=False)
        else:
            # Stream in row-group batches
            text += f"(Large file — showing first {STREAM_THRESHOLD:,} rows)\n\n"
            rows_shown = 0
            for i in range(pf.num_row_groups):
                rg = pf.read_row_group(i)
                df = rg.to_pandas()
                remaining = STREAM_THRESHOLD - rows_shown
                if remaining <= 0:
                    break
                text += df.head(remaining).to_string(index=False, header=(rows_shown == 0)) + "\n"
                rows_shown += len(df)

        return text

    @staticmethod
    def _extract_csv(file_path: str) -> str:
        """Extract CSV with robust encoding and delimiter detection"""
        import pandas as pd
        
        # Detect encoding
        encoding = TextExtractor._detect_encoding(file_path)
        
        # Try different delimiters
        delimiters = [',', ';', '\t', '|']
        df = None
        
        for delimiter in delimiters:
            try:
                df = pd.read_csv(file_path, encoding=encoding, delimiter=delimiter, on_bad_lines='skip')
                if len(df.columns) > 1:  # Valid CSV should have multiple columns
                    break
            except Exception:
                continue
        
        if df is None or df.empty:
            # Fallback: try with default settings
            try:
                df = pd.read_csv(file_path, encoding='utf-8', on_bad_lines='skip')
            except Exception as e:
                logger.warning(f"Failed to parse CSV {file_path}: {e}")
                return f"CSV File: {os.path.basename(file_path)}\n\nError: Could not parse CSV file."
        
        text = f"CSV File: {os.path.basename(file_path)}\n\n"
        text += f"Columns: {', '.join(df.columns)}\n\n"
        text += f"Number of rows: {len(df)}\n\n"
        # Include all rows for RAG (chunking handles size downstream)
        text += "Data:\n"
        text += df.to_string(index=False)
        return text
    
    @staticmethod
    def _detect_encoding(file_path: str) -> str:
        """Detect file encoding using chardet"""
        try:
            import chardet
            with open(file_path, 'rb') as f:
                result = chardet.detect(f.read(100000))  # Read first 100KB
            detected = result.get('encoding', 'utf-8')
            logger.info(f"Detected encoding for {file_path}: {detected}")
            return detected
        except ImportError:
            logger.warning("chardet not installed, using utf-8")
            return 'utf-8'
        except Exception as e:
            logger.warning(f"Encoding detection failed: {e}, using utf-8")
            return 'utf-8'


    @staticmethod
    def _extract_yaml(file_path: str) -> str:
        """Extract YAML/YML files — flattens into readable key-value text."""
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                data = yaml.safe_load(f)
        except ImportError:
            # Fallback: read as plain text
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f"YAML File: {os.path.basename(file_path)}\n\n{f.read()}"
        except Exception:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f"YAML File: {os.path.basename(file_path)}\n\n{f.read()}"

        def _flat(obj, prefix=""):
            lines = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}.{k}" if prefix else str(k)
                    lines.extend(_flat(v, key))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    lines.extend(_flat(item, f"{prefix}[{i}]"))
            else:
                lines.append(f"{prefix}: {obj}")
            return lines

        text = f"YAML File: {os.path.basename(file_path)}\n\n"
        text += "\n".join(_flat(data or {}))
        return text

    @staticmethod
    def _extract_toml(file_path: str) -> str:
        """Extract TOML files."""
        try:
            import tomllib  # Python 3.11+
            with open(file_path, "rb") as f:
                data = tomllib.load(f)
        except ImportError:
            try:
                import tomli as tomllib  # pip install tomli
                with open(file_path, "rb") as f:
                    data = tomllib.load(f)
            except ImportError:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return f"TOML File: {os.path.basename(file_path)}\n\n{f.read()}"

        import json as _json
        text = f"TOML File: {os.path.basename(file_path)}\n\n"
        text += _json.dumps(data, indent=2, default=str)
        return text

    @staticmethod
    def _extract_ini(file_path: str) -> str:
        """Extract INI/CFG/CONF config files."""
        import configparser
        config = configparser.ConfigParser()
        try:
            config.read(file_path, encoding="utf-8")
            lines = []
            for section in config.sections():
                lines.append(f"[{section}]")
                for key, val in config.items(section):
                    lines.append(f"{key} = {val}")
                lines.append("")
            if lines:
                return f"Config File: {os.path.basename(file_path)}\n\n" + "\n".join(lines)
        except Exception:
            pass
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f"Config File: {os.path.basename(file_path)}\n\n{f.read()}"

    @staticmethod
    def _extract_code(file_path: str) -> str:
        """Extract source code files — adds language header + line numbers."""
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".java": "Java", ".cpp": "C++", ".c": "C", ".go": "Go",
            ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".sh": "Shell",
            ".sql": "SQL",
        }
        lang = lang_map.get(ext, "Code")
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        text = f"{lang} Source: {os.path.basename(file_path)}\n"
        text += f"Lines: {source.count(chr(10)) + 1}\n\n"
        # Add line numbers (helps LLM reason about specific lines)
        lines = source.splitlines()
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        return text + numbered

    @staticmethod
    def _extract_notebook(file_path: str) -> str:
        """Extract Jupyter Notebook (.ipynb) — reads code + markdown cells."""
        import json as _json
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            nb = _json.load(f)
        cells = nb.get("cells", [])
        parts = [f"Jupyter Notebook: {os.path.basename(file_path)}\n"]
        for i, cell in enumerate(cells):
            ctype = cell.get("cell_type", "code")
            source = "".join(cell.get("source", []))
            parts.append(f"--- Cell {i+1} ({ctype}) ---\n{source}")
            # Include text outputs (skip binary/image)
            for out in cell.get("outputs", []):
                if out.get("output_type") in ("stream", "execute_result", "display_data"):
                    txt = "".join(out.get("text", out.get("data", {}).get("text/plain", [])))
                    if txt.strip():
                        parts.append(f"Output:\n{txt[:500]}")
        return "\n\n".join(parts)


class VectorDB:
    def __init__(self):
        self.client = _get_chromadb().PersistentClient(path="./data/chroma")
        self.embedding_manager = EmbeddingManager()
        self._current_dimension = None
        self._collections = {}
        self.collection = self._get_collection()

        # Full-text search engine (keyword / hybrid support)
        try:
            from app.search.full_text_search import FullTextSearchEngine
            self.ft_engine = FullTextSearchEngine()
        except Exception:  # noqa: broad-except OK for optional feature
            self.ft_engine = None

        # Circuit breaker — guards ChromaDB calls, falls back to BM25
        try:
            from app.services.circuit_breaker import CircuitBreaker
            self._cb = CircuitBreaker("chromadb", failure_threshold=5, recovery_timeout=60)
        except Exception:
            self._cb = None

    def _get_collection_name(self, org_id: Optional[str] = None) -> str:
        """Get dimension-tagged collection name for the active embedding provider."""
        try:
            dim = self.embedding_manager.get_dimension()
        except Exception:
            dim = 1536  # Fallback
        if not org_id or org_id == "default":
            return f"documents_{dim}"
        safe_org = "".join(c for c in org_id if c.isalnum() or c in ("_", "-")).strip()
        if not safe_org:
            safe_org = "org"
        return f"{safe_org}_documents_{dim}"

    def _get_collection(self, org_id: Optional[str] = None):
        """Get or create the ChromaDB collection matching the current embedding dimension."""
        name = self._get_collection_name(org_id)
        try:
            dim = self.embedding_manager.get_dimension()
        except Exception:
            dim = None
        self._current_dimension = dim
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(name)
        return self._collections[name]

    def refresh_collection(self):
        """Refresh the collection if the embedding dimension has changed."""
        try:
            new_dim = self.embedding_manager.get_dimension()
        except Exception:
            return
        if new_dim != self._current_dimension:
            logger.info(
                "Embedding dimension changed (%s -> %s), switching collection",
                self._current_dimension, new_dim,
            )
            self._collections = {}
            self.collection = self._get_collection()

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Dict = None,
        chunk_size: int = 512,
        overlap: int = 64,
        org_id: Optional[str] = None,
        doc_type: str = "narrative",
        doc_subtype: str = "general",
        use_chunking_optimizer: bool = True,
        embedding_hint: Optional[str] = None,
    ):
        self.refresh_collection()
        collection = self._get_collection(org_id)

        if use_chunking_optimizer:
            try:
                from app.services.chunking_optimizer import ChunkingOptimizer
                result = ChunkingOptimizer().optimize(
                    text,
                    doc_type=doc_type,
                    doc_subtype=doc_subtype,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                chunks = result.chunks
                if metadata is not None:
                    metadata["chunking_strategy"] = result.strategy
                    metadata["chunking_score"] = result.score
            except Exception as _ce:
                logger.warning("ChunkingOptimizer failed, falling back: %s", _ce)
                chunks = self._chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        else:
            chunks = self._chunk_text(text, chunk_size=chunk_size, overlap=overlap)

        # Use multilingual model if language detection requested it
        if embedding_hint and embedding_hint != "default":
            embeddings = self.embedding_manager.embed_with_model(chunks, embedding_hint)
        else:
            embeddings = self._get_embeddings(chunks)

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "chunk_id": i, **(metadata or {})} for i in range(len(chunks))]

        collection.add(
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )

        # Also index into full-text search engine
        if self.ft_engine is not None:
            try:
                self.ft_engine.index_document(
                    doc_id,
                    text,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.warning("Full-text index failed for %s: %s", doc_id, e)

    def search(
        self,
        query: str,
        top_k: int = 5,
        search_mode: str = "semantic",
        org_id: Optional[str] = None,
        where_filter: Optional[Dict] = None,
    ) -> List[Dict]:
        """Search documents using semantic, keyword, or hybrid mode.

        Args:
            where_filter: Optional ChromaDB metadata filter, e.g.
                          {"doc_id": {"$eq": "abc123"}} to restrict
                          Stage-2 retrieval to a specific document.
        """
        semantic_results: List[Dict] = []
        keyword_results: List[Dict] = []

        # Semantic search (ChromaDB) — wrapped with circuit breaker
        if search_mode in ("semantic", "hybrid"):
            self.refresh_collection()
            collection = self._get_collection(org_id)
            query_embedding = self._get_embeddings([query])[0]
            query_kwargs: Dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            def _chromadb_query():
                return collection.query(**query_kwargs)

            def _bm25_fallback():
                """BM25 fallback when ChromaDB is unavailable."""
                if self.ft_engine is None:
                    logger.warning("VectorDB: both ChromaDB and BM25 unavailable")
                    return None
                logger.warning("VectorDB: ChromaDB circuit open — falling back to BM25")
                kw = self.ft_engine.search_keyword(query, top_k=top_k)
                # Return a ChromaDB-compatible structure so the parser below works
                return {
                    "documents": [[r["document"] for r in kw]],
                    "metadatas": [[r["metadata"] for r in kw]],
                    "distances": [[r["score"] for r in kw]],
                } if kw else None

            if self._cb is not None:
                raw = self._cb.call(_chromadb_query, fallback=_bm25_fallback)
            else:
                try:
                    raw = _chromadb_query()
                except Exception as _e:
                    logger.warning("ChromaDB query failed (no CB): %s", _e)
                    raw = _bm25_fallback()

            if raw and raw.get("documents") and raw["documents"][0]:
                semantic_results = [
                    {"document": doc, "metadata": meta, "score": score}
                    for doc, meta, score in zip(
                        raw["documents"][0],
                        raw["metadatas"][0],
                        raw["distances"][0],
                    )
                ]

        # Keyword search (BM25) — filter by doc_id if where_filter provided
        if search_mode in ("keyword", "hybrid") and self.ft_engine is not None:
            try:
                kw_results = self.ft_engine.search_keyword(query, top_k=top_k)
                # Apply doc_id filter manually if provided
                if where_filter and "$eq" in str(where_filter):
                    filter_doc_id = None
                    if "doc_id" in where_filter:
                        val = where_filter["doc_id"]
                        filter_doc_id = val.get("$eq") if isinstance(val, dict) else val
                    if filter_doc_id:
                        kw_results = [
                            r for r in kw_results
                            if r.get("metadata", {}).get("doc_id") == filter_doc_id
                        ]
                keyword_results = kw_results
            except Exception as e:
                logger.warning("Keyword search failed: %s", e)

        # Return based on mode
        if search_mode == "semantic":
            return semantic_results
        elif search_mode == "keyword":
            return keyword_results
        else:  # hybrid
            if not keyword_results:
                return semantic_results
            if not semantic_results:
                return keyword_results
            from app.search.full_text_search import FullTextSearchEngine
            return FullTextSearchEngine.hybrid_merge(
                semantic_results, keyword_results, alpha=0.5, top_k=top_k
            )

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        """Split text into overlapping word-level chunks."""
        words = text.split()
        chunks = []
        step = max(chunk_size - overlap, 1)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            if i + chunk_size >= len(words):
                break
        return chunks

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using the active embedding provider."""
        return self.embedding_manager.embed(texts)


class RAGEngine:
    def __init__(self):
        self.vectordb = VectorDB()
        self.llm_manager = LLMManager()
        self.llm_client = None
        self._query_cache_ttl = int(os.getenv("QUERY_CACHE_TTL", "300"))
        # Use Redis if available and configured, otherwise fall back to in-memory dict
        self._redis = None
        self._query_cache: dict = {}
        if os.getenv("ENABLE_QUERY_CACHE", "false").lower() in ("1", "true", "yes"):
            try:
                import redis as _redis_mod
                _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                _r = _redis_mod.from_url(_redis_url, socket_connect_timeout=2)
                _r.ping()
                self._redis = _r
                logger.info("Query cache: Redis connected at %s", _redis_url)
            except Exception as _re:
                logger.info("Query cache: Redis unavailable (%s) — using in-memory cache", _re)

        # Import here to avoid circular import at module level
        from app.services.rag_config_service import RAGConfigurationService
        self.config_service = RAGConfigurationService()

    def _get_llm_client(self):
        if self.llm_client is None:
            available_providers = self.llm_manager.get_available_providers()
            for provider in available_providers:
                try:
                    models = self.llm_manager.get_provider_models(provider)
                    if models:
                        self.llm_client = self.llm_manager.get_langchain_llm(provider, models[0])
                        break
                except Exception as e:
                    logger.warning("Failed to get LLM from %s: %s", provider, e)
                    continue

            if self.llm_client is None:
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    from langchain_openai import ChatOpenAI
                    self.llm_client = ChatOpenAI(
                        api_key=api_key,
                        model="gpt-3.5-turbo",
                    )
                else:
                    raise ValueError(
                        "No LLM provider configured. "
                        "Configure a provider in the UI or set OPENAI_API_KEY."
                    )
        return self.llm_client

    # ── HyDE: Hypothetical Document Embeddings ─────────────────────────────────

    def _hyde_expand(self, query: str) -> str:
        """
        Generate a hypothetical document passage that would answer *query*,
        then return it as an enriched retrieval query (HyDE technique).

        Closes the vocabulary gap between short queries and long document chunks.
        Falls back to the original query on any error.
        """
        try:
            from langchain_core.messages import HumanMessage as HM
            llm = self._get_llm_client()
            prompt = (
                "Write a short, factual passage (2-4 sentences) that would directly "
                f"answer the following question:\n\nQuestion: {query}\n\nPassage:"
            )
            response = llm.invoke([HM(content=prompt)])
            expanded = response.content.strip()
            if expanded:
                logger.debug("HyDE expanded query for: %s", query[:60])
                return expanded
        except Exception as exc:
            logger.debug("HyDE expansion failed (falling back to original): %s", exc)
        return query

    # ── Knowledge Strips ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_knowledge_strips(query: str, chunks: List[str]) -> List[str]:
        """
        Filter each chunk to sentences containing ≥2 query keywords.

        Reduces noise from irrelevant sentences in long chunks, which lowers
        hallucination risk when chunks partially match the query topic.
        Falls back to the full chunk when no sentences qualify.
        """
        _stop = {
            "what", "how", "who", "when", "where", "why", "which", "is", "are",
            "was", "were", "the", "a", "an", "and", "or", "but", "in", "on",
            "at", "to", "for", "of", "with", "by", "from", "about", "does",
            "do", "did", "can", "could", "should", "would", "will", "has",
            "have", "had", "be", "been", "being", "this", "that", "these",
            "those", "it",
        }
        keywords = {
            w for w in re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())
            if w not in _stop
        }
        if not keywords:
            return chunks  # can't filter without keywords

        stripped = []
        for chunk in chunks:
            sentences = re.split(r"(?<=[.!?])\s+", chunk)
            relevant = [
                s for s in sentences
                if sum(1 for kw in keywords if kw in s.lower()) >= 2
            ]
            stripped.append(" ".join(relevant) if relevant else chunk)
        return stripped

    def upload_document(
        self,
        file_path: str,
        doc_id: str,
        username: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        access_level: str = "private",
        allowed_users: Optional[List[str]] = None,
        allowed_groups: Optional[List[str]] = None,
        allowed_roles: Optional[List[str]] = None,
        chunk_size_override: Optional[int] = None,
        overlap_override: Optional[int] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        doc_type: str = "narrative",
        doc_subtype: str = "general",
    ):
        from app.services.rbac_service import RBACService
        rbac_service = RBACService()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id", "default")
        owner = username or "system"

        chunk_size, overlap, _, _, _ = self.config_service.get_active_params(username)
        # Auto-config overrides take precedence over user's saved RAG config
        if chunk_size_override is not None:
            chunk_size = chunk_size_override
        if overlap_override is not None:
            overlap = overlap_override

        text = TextExtractor.extract_text(file_path)

        # ── Text preprocessing (OCR fix + coreference) ───────────────────────
        try:
            from app.services.text_preprocessor import TextPreprocessor
            _doc_type_hint = (extra_metadata or {}).get("doc_type", doc_type)
            text = TextPreprocessor().preprocess(
                text,
                doc_type=_doc_type_hint,
                fix_ocr=True,
                resolve_coreferences=True,
            )
        except Exception as _pe:
            logger.debug("TextPreprocessor skipped: %s", _pe)

        # ── Language detection → auto-switch embedding if multilingual ────────
        _embedding_hint: Optional[str] = None
        try:
            from app.services.language_detector import LanguageDetector
            lang_result = LanguageDetector().detect(text[:3000])
            detected_lang = lang_result.language
            if lang_result.is_multilingual:
                _embedding_hint = lang_result.embedding_hint
                logger.info(
                    "Multilingual document detected (lang=%s) — will embed with %s",
                    detected_lang, _embedding_hint,
                )
        except Exception as _e:
            detected_lang = "en"
            logger.debug("Language detection skipped: %s", _e)

        meta = {
            "filename": os.path.basename(file_path),
            "source_type": "upload",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "owner": owner,
            "access_level": access_level,
            "allowed_users": allowed_users or [],
            "allowed_groups": allowed_groups or [],
            "allowed_roles": allowed_roles or [],
            "language": detected_lang,
        }
        if source_metadata:
            meta.update(source_metadata)
        if extra_metadata:
            meta.update(extra_metadata)
        # ── Document version / date awareness ────────────────────────────────
        try:
            doc_date = _extract_document_date(text)
            if doc_date:
                meta["doc_date"] = doc_date
                logger.debug("Document date detected: %s for %s", doc_date, doc_id)
        except Exception as _de:
            logger.debug("Date extraction failed: %s", _de)

        # Pull doc_type/subtype from extra_metadata if provided (from main.py pipeline)
        _doc_type = (extra_metadata or {}).get("doc_type", doc_type)
        _doc_subtype = (extra_metadata or {}).get("doc_subtype", doc_subtype)

        self.vectordb.add_document(
            doc_id,
            text,
            meta,
            chunk_size=chunk_size,
            overlap=overlap,
            org_id=org_id,
            doc_type=_doc_type,
            doc_subtype=_doc_subtype,
            embedding_hint=_embedding_hint,
        )

        rbac_service.set_document_permissions(
            document_id=doc_id,
            org_id=org_id,
            owner_username=owner,
            access_level=access_level,
            allowed_users=allowed_users,
            allowed_groups=allowed_groups,
            allowed_roles=allowed_roles,
        )

        # ── Background knowledge graph building ───────────────────────────
        # Build KG from document text (non-blocking — errors are suppressed)
        try:
            from app.graph.knowledge_graph import KnowledgeGraphBuilder
            builder = KnowledgeGraphBuilder(username=username)
            # Use first 3000 chars to keep LLM cost low
            _text_sample = text[:3000]
            _llm = self._get_llm_client()
            builder.build_from_text(
                _text_sample,
                _llm,
                source_doc=os.path.basename(file_path),
            )
        except Exception as _kg_err:
            logger.debug("Knowledge graph build skipped for %s: %s", doc_id, _kg_err)

    def query(self, question: str, username: Optional[str] = None) -> str:
        from app.services.rbac_service import RBACService
        rbac_service = RBACService()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id")

        _, _, top_k, _, search_mode = self.config_service.get_active_params(username)
        cache_enabled = os.getenv("ENABLE_QUERY_CACHE", "false").lower() in ("1", "true", "yes")
        cache_key = f"rapid:q:{org_id}:{username}:{question}:{top_k}:{search_mode}"
        if cache_enabled:
            if self._redis:
                try:
                    _hit = self._redis.get(cache_key)
                    if _hit:
                        return _hit.decode()
                except Exception:
                    pass
            else:
                _entry = self._query_cache.get(cache_key)
                if _entry and time.time() - _entry["ts"] < self._query_cache_ttl:
                    return _entry["answer"]

        results = self.vectordb.search(question, top_k=top_k, search_mode=search_mode, org_id=org_id)
        if user_ctx:
            results = rbac_service.filter_results(results, user_ctx)

        if not results:
            return "No accessible documents matched your query."
        context = "\n".join([r["document"] for r in results])

        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"

        llm_client = self._get_llm_client()
        from langchain_core.messages import HumanMessage
        response = llm_client.invoke([HumanMessage(content=prompt)])
        answer = response.content

        # Add source citations
        sources = [f"Source {i+1}: {r['metadata'].get('filename', 'unknown')}" for i, r in enumerate(results)]
        final_answer = f"{answer}\n\n" + "\n".join(sources)
        if cache_enabled:
            if self._redis:
                try:
                    self._redis.setex(cache_key, self._query_cache_ttl, final_answer)
                except Exception:
                    pass
            else:
                self._query_cache[cache_key] = {"answer": final_answer, "ts": time.time()}
        return final_answer
    
    def query_with_sources(self, question: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Like query() but returns a structured dict with answer + sources list."""
        from app.services.rbac_service import RBACService
        rbac_service = RBACService()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id")

        _, _, top_k, _, search_mode = self.config_service.get_active_params(username)
        results = self.vectordb.search(question, top_k=top_k, search_mode=search_mode, org_id=org_id)
        if user_ctx:
            results = rbac_service.filter_results(results, user_ctx)

        if not results:
            return {"answer": "No accessible documents matched your query.", "sources": [], "context_chunks": []}

        context = "\n".join([r["document"] for r in results])
        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        llm_client = self._get_llm_client()
        from langchain_core.messages import HumanMessage as HM
        response = llm_client.invoke([HM(content=prompt)])
        answer = response.content

        sources = [
            {
                "filename": r["metadata"].get("filename", "unknown"),
                "chunk_id": r["metadata"].get("chunk_id", 0),
                "doc_id": r["metadata"].get("doc_id", ""),
            }
            for r in results
        ]
        return {"answer": answer, "sources": sources, "context_chunks": [r["document"] for r in results]}

    def stream_query(self, question: str, username: Optional[str] = None):
        """Stream the LLM answer token by token after retrieving RAG context.

        Yields string tokens. The final yield includes a sources footer.
        """
        from app.services.rbac_service import RBACService
        rbac_service = RBACService()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id")

        _, _, top_k, _, search_mode = self.config_service.get_active_params(username)
        results = self.vectordb.search(question, top_k=top_k, search_mode=search_mode, org_id=org_id)
        if user_ctx:
            results = rbac_service.filter_results(results, user_ctx)

        if not results:
            yield "No accessible documents matched your query."
            return

        context = "\n".join([r["document"] for r in results])
        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        llm_client = self._get_llm_client()

        from langchain_core.messages import HumanMessage as HM
        try:
            for chunk in llm_client.stream([HM(content=prompt)]):
                token = getattr(chunk, "content", "")
                if token:
                    yield token
        except Exception as e:
            logger.warning("Streaming failed, falling back: %s", e)
            response = llm_client.invoke([HM(content=prompt)])
            yield response.content

        # Append source citations at end
        if results:
            yield "\n\n**Sources:**\n" + "\n".join(
                f"- 📄 {r['metadata'].get('filename', 'unknown')}"
                for r in results
            )

    # ─────────────────────────────────────────────────────────────────────────
    # TWO-STAGE RETRIEVAL + CONFIDENCE-SCORED QUERY
    # ─────────────────────────────────────────────────────────────────────────

    def _two_stage_retrieve(
        self,
        question: str,
        org_id: Optional[str],
        user_ctx: Optional[Dict],
        rbac_service: Any,
        broad_k: int = 20,
        search_mode: str = "hybrid",
    ) -> List[Dict]:
        """
        Stage 1: Broad retrieval (wide net across all documents).
        Stage 2: Per-document focused retrieval using each document's
                 auto-detected optimal config.

        Returns the merged, RBAC-filtered list of chunks.
        """
        from collections import Counter
        import sqlite3 as _sqlite3
        import json as _json
        from app.services.auto_config_service import AutoConfigService

        auto_cfg = AutoConfigService()

        # ── Stage 1: broad pass ───────────────────────────────────────────
        broad_results = self.vectordb.search(
            question, top_k=broad_k, search_mode=search_mode, org_id=org_id
        )
        if user_ctx:
            broad_results = rbac_service.filter_results(broad_results, user_ctx)

        if not broad_results:
            return []

        # Count which doc_ids appeared and how many times
        doc_hits: Counter = Counter(
            r["metadata"].get("doc_id", "") for r in broad_results
        )
        # Keep docs with at least 1 hit (all that appeared)
        relevant_doc_ids = [doc_id for doc_id, _ in doc_hits.most_common() if doc_id]

        # ── Stage 2: focused pass per document ───────────────────────────
        # Load doc metadata from SQLite for type lookup
        doc_type_map: Dict[str, tuple] = {}
        try:
            _con = _sqlite3.connect(os.path.join("data", "users.db"))
            _cur = _con.execute(
                "SELECT doc_id, doc_type, doc_subtype FROM documents WHERE doc_id IN ({})".format(
                    ",".join("?" * len(relevant_doc_ids))
                ),
                relevant_doc_ids,
            )
            for row in _cur.fetchall():
                doc_type_map[row[0]] = (row[1] or "narrative", row[2] or "general")
            _con.close()
        except Exception as e:
            logger.debug("Could not load doc type map: %s", e)

        stage2_results: List[Dict] = []
        for doc_id in relevant_doc_ids:
            doc_type, doc_subtype = doc_type_map.get(doc_id, ("narrative", "general"))
            cfg = auto_cfg.get_pipeline_config(doc_type, doc_subtype)

            focused = self.vectordb.search(
                question,
                top_k=cfg.top_k or 5,
                search_mode=cfg.search_mode or "hybrid",
                org_id=org_id,
                where_filter={"doc_id": {"$eq": doc_id}},
            )
            if user_ctx:
                focused = rbac_service.filter_results(focused, user_ctx)
            stage2_results.extend(focused)

        if not stage2_results:
            # Safety: fall back to broad results if Stage 2 empty
            return _apply_recency_boost(broad_results)

        # Apply recency boost before merging
        stage2_results = _apply_recency_boost(stage2_results)

        # Merge Stage 2 results with RRF across all documents
        try:
            from app.search.full_text_search import FullTextSearchEngine
            # Build per-doc ranked lists and merge
            from collections import defaultdict
            per_doc: Dict[str, List[Dict]] = defaultdict(list)
            for r in stage2_results:
                per_doc[r["metadata"].get("doc_id", "unknown")].append(r)

            if len(per_doc) == 1:
                return stage2_results  # single doc — no merge needed

            # Interleave with simple RRF across doc lists
            merged = FullTextSearchEngine.hybrid_merge(
                stage2_results, stage2_results, alpha=0.5, top_k=broad_k
            )
            return merged if merged else stage2_results
        except Exception:
            return stage2_results

    def two_stage_query(
        self,
        question: str,
        username: Optional[str] = None,
        use_confidence: bool = True,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Full two-stage retrieval + confidence-scored generation.

        Returns:
            {
                answer: str,
                sources: list,
                confidence: ConfidenceResult,
                retries: int,
                context_chunks: list,
            }
        """
        from app.services.rbac_service import RBACService
        from app.services.confidence_scorer import ConfidenceScorer

        rbac_service = RBACService()
        scorer = ConfidenceScorer()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id")

        llm_client = self._get_llm_client()
        from langchain_core.messages import HumanMessage as HM

        broad_k = 20
        _search_mode_cycle = ["hybrid", "semantic", "keyword"]
        search_mode_idx = 0
        confidence = None
        retries = 0

        for attempt in range(max_retries + 1):
            current_search_mode = _search_mode_cycle[search_mode_idx]
            # ── Retrieve ──────────────────────────────────────────────────
            try:
                results = self._two_stage_retrieve(
                    question, org_id, user_ctx, rbac_service,
                    broad_k=broad_k, search_mode=current_search_mode,
                )
                # Apply recency boost: re-ranks results giving newer docs a slight edge
                results = _apply_recency_boost(results)
            except Exception as e:
                logger.warning("Two-stage retrieve failed (attempt %d): %s", attempt, e)
                results = []

            if not results:
                # Hard fallback: standard single-stage query
                return {
                    "answer": "No accessible documents matched your query.",
                    "sources": [],
                    "confidence": None,
                    "retries": attempt,
                    "context_chunks": [],
                }

            # ── Knowledge Graph augmentation ──────────────────────────────
            kg_context = ""
            try:
                from app.graph.knowledge_graph import GraphQueryEngine
                gqe = GraphQueryEngine(username=username)
                if gqe.graph.number_of_nodes() > 0:
                    kg_results = gqe.search_entities(question)
                    if kg_results:
                        kg_lines = []
                        for ent in kg_results[:5]:
                            neighbors = gqe.get_neighbors(ent["name"])
                            if neighbors:
                                rels = "; ".join(
                                    f"{n['entity']} ({n['relation']})"
                                    for n in neighbors[:3]
                                )
                                kg_lines.append(f"• {ent['name']} [{ent.get('type','')}]: {rels}")
                        if kg_lines:
                            kg_context = (
                                "\n\nKnowledge Graph Context:\n"
                                + "\n".join(kg_lines)
                                + "\n"
                            )
            except Exception as _kg_e:
                logger.debug("Knowledge graph augmentation skipped: %s", _kg_e)

            # ── Knowledge strips: keep only sentences relevant to query ───
            stripped_chunks = self._extract_knowledge_strips(
                question, [r["document"] for r in results]
            )

            # ── Generate ──────────────────────────────────────────────────
            context = "\n\n---\n\n".join(stripped_chunks)
            prompt = (
                f"Use the following context to answer the question.\n"
                f"If the context does not contain enough information, say so clearly.\n\n"
                f"Context:\n{context}"
                f"{kg_context}\n\n"
                f"Question: {question}\n\n"
                f"Answer:"
            )
            try:
                response = llm_client.invoke([HM(content=prompt)])
                answer = response.content
            except Exception as e:
                logger.warning("LLM generation failed: %s", e)
                answer = "I encountered an error generating an answer. Please try again."
                break

            # ── Score ─────────────────────────────────────────────────────
            if use_confidence:
                confidence = scorer.score(
                    query=question,
                    chunks=stripped_chunks,  # use stripped for scoring too
                    answer=answer,
                    llm_client=llm_client,
                    use_llm_faithfulness=(attempt == 0),  # LLM check only on first try
                )
                logger.info(
                    "Attempt %d: confidence=%.2f (%s) retry_reason=%s",
                    attempt, confidence.overall, confidence.verdict, confidence.retry_reason,
                )

                if confidence.passed() or attempt >= max_retries:
                    break

                # ── Retry strategy ────────────────────────────────────────
                retries += 1
                if confidence.retry_reason == "retrieval":
                    # Cycle search mode: hybrid → semantic → keyword
                    search_mode_idx = min(search_mode_idx + 1, len(_search_mode_cycle) - 1)
                    broad_k = min(broad_k + 10, 30)
                    logger.info(
                        "Retry %d: switching search_mode to '%s', broad_k=%d",
                        retries, _search_mode_cycle[search_mode_idx], broad_k,
                    )
                elif confidence.retry_reason == "faithfulness":
                    # Get more context chunks
                    broad_k = min(broad_k + 5, 30)
                elif confidence.retry_reason == "completeness":
                    # Broader search
                    broad_k = min(broad_k + 5, 30)
            else:
                # No confidence scoring — just one pass
                break

        # ── Unanswerable detection ─────────────────────────────────────────────
        # When the ConfidenceScorer is certain the context cannot answer the
        # question, return a clear "I don't know" instead of a hallucinated answer.
        if use_confidence and confidence is not None and confidence.unanswerable:
            logger.info("Query flagged as unanswerable — returning cannot-answer response")
            return {
                "answer": (
                    "I couldn't find enough information in the available documents "
                    "to answer this question. Please ensure the relevant documents "
                    "have been uploaded, or rephrase your question."
                ),
                "sources": [],
                "confidence": confidence,
                "retries": retries,
                "context_chunks": [],
                "unanswerable": True,
            }

        # ── Conflict detection surfacing ───────────────────────────────────────
        # When retrieved chunks contain contradicting numeric facts, append a
        # visible warning so the user knows to verify the source documents.
        if use_confidence and confidence is not None and confidence.conflicts:
            conflict_notes = "; ".join(
                reason for _, _, reason in confidence.conflicts[:3]
            )
            answer = (
                answer
                + f"\n\n⚠️ **Note:** Conflicting information was detected in the "
                f"source documents: {conflict_notes}"
            )

        sources = [
            {
                "filename": r["metadata"].get("filename", "unknown"),
                "chunk_id": r["metadata"].get("chunk_id", 0),
                "doc_id": r["metadata"].get("doc_id", ""),
                "doc_type": r["metadata"].get("doc_type", ""),
            }
            for r in results
        ]

        return {
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "retries": retries,
            "context_chunks": [r["document"] for r in results],
        }

    def two_stage_stream_query(
        self,
        question: str,
        username: Optional[str] = None,
    ):
        """
        Two-stage retrieval + token-by-token streaming.

        Runs retrieval with two-stage logic first (blocking),
        then streams the LLM answer. Yields string tokens.
        Appends confidence info and sources at end.
        """
        from app.services.rbac_service import RBACService
        from app.services.confidence_scorer import ConfidenceScorer

        rbac_service = RBACService()
        scorer = ConfidenceScorer()

        user_ctx = rbac_service.get_user(username) if username else None
        org_id = (user_ctx or {}).get("org_id")

        llm_client = self._get_llm_client()
        from langchain_core.messages import HumanMessage as HM

        # Retrieval (blocking — must complete before streaming starts)
        try:
            results = self._two_stage_retrieve(
                question, org_id, user_ctx, rbac_service, broad_k=20
            )
        except Exception as e:
            logger.warning("Two-stage retrieve failed: %s", e)
            results = []

        if not results:
            yield "No accessible documents matched your query."
            return

        context = "\n\n---\n\n".join(r["document"] for r in results)
        prompt = (
            f"Use the following context to answer the question.\n"
            f"If the context does not contain enough information, say so clearly.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )

        # Collect tokens for confidence scoring after stream
        full_answer_tokens: List[str] = []

        try:
            for chunk in llm_client.stream([HM(content=prompt)]):
                token = getattr(chunk, "content", "")
                if token:
                    full_answer_tokens.append(token)
                    yield token
        except Exception as e:
            logger.warning("Streaming failed, falling back: %s", e)
            response = llm_client.invoke([HM(content=prompt)])
            full_answer_tokens = [response.content]
            yield response.content

        # ── Confidence score (post-stream) ────────────────────────────────
        full_answer = "".join(full_answer_tokens)
        try:
            confidence = scorer.score(
                query=question,
                chunks=[r["document"] for r in results],
                answer=full_answer,
                llm_client=None,  # no extra LLM call during streaming
                use_llm_faithfulness=False,
            )
            if confidence.verdict == "low":
                yield (
                    f"\n\n> ⚠️ **Low confidence** ({confidence.overall:.0%}): "
                    f"{confidence.retry_suggestion or 'Consider rephrasing your question.'}"
                )
            elif confidence.verdict == "medium":
                yield f"\n\n> ℹ️ **Confidence:** {confidence.overall:.0%} — answer may be partial."
        except Exception as e:
            logger.debug("Post-stream confidence scoring failed: %s", e)

        # Sources footer
        if results:
            seen_files = []
            for r in results:
                fname = r["metadata"].get("filename", "unknown")
                if fname not in seen_files:
                    seen_files.append(fname)
            yield "\n\n**Sources:**\n" + "\n".join(f"- 📄 {f}" for f in seen_files)

    def convert_csv_to_database(self, csv_path: str, db_name: str = None) -> Dict[str, Any]:
        """Convert CSV file to SQLite database for querying"""
        import pandas as pd
        import sqlite3
        
        try:
            # Detect encoding
            encoding = TextExtractor._detect_encoding(csv_path)
            
            # Read CSV
            df = pd.read_csv(csv_path, encoding=encoding, on_bad_lines='skip')
            
            if df.empty:
                return {"error": "CSV file is empty"}
            
            # Generate database name if not provided
            if db_name is None:
                db_name = os.path.splitext(os.path.basename(csv_path))[0]
            
            # Create database directory
            db_dir = "./data/csv_databases"
            os.makedirs(db_dir, exist_ok=True)
            
            db_path = os.path.join(db_dir, f"{db_name}.db")
            table_name = "data"
            
            # Infer column types
            column_types = self._infer_column_types(df)
            
            # Create database and table
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create table with inferred types
            columns_def = ", ".join([f'"{col}" {dtype}' for col, dtype in column_types.items()])
            create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_def})'
            cursor.execute(create_table_sql)
            
            # Insert data
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            
            conn.commit()
            row_count = len(df)
            conn.close()
            
            logger.info(f"Converted CSV to database: {db_path} ({row_count} rows)")
            
            return {
                "success": True,
                "db_path": db_path,
                "table_name": table_name,
                "row_count": row_count,
                "columns": list(df.columns),
                "column_types": column_types
            }
            
        except Exception as e:
            logger.error(f"CSV to database conversion failed: {e}")
            return {"error": str(e)}
    
    def _infer_column_types(self, df) -> Dict[str, str]:
        """Infer SQL types from pandas DataFrame"""
        import pandas as pd
        
        type_map = {}
        for col in df.columns:
            # Check for nulls
            if df[col].isna().all():
                type_map[col] = "TEXT"
                continue
            
            # Try to infer type from non-null values
            sample = df[col].dropna()
            
            if pd.api.types.is_integer_dtype(sample):
                type_map[col] = "INTEGER"
            elif pd.api.types.is_float_dtype(sample):
                type_map[col] = "REAL"
            elif pd.api.types.is_bool_dtype(sample):
                type_map[col] = "INTEGER"  # SQLite uses INTEGER for boolean
            elif pd.api.types.is_datetime64_any_dtype(sample):
                type_map[col] = "DATETIME"
            else:
                # Try to detect dates in string format
                try:
                    pd.to_datetime(sample.head(100), errors='raise')
                    type_map[col] = "DATETIME"
                except (ValueError, TypeError):
                    type_map[col] = "TEXT"
        
        return type_map
