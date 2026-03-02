"""
Chunking Optimizer for Intelligent Auto-RAG.

Implements 9 chunking strategies and automatically picks the best one
for each document type using a rule-based + retrieval-quality scoring system.

Strategies:
  1. fixed_word       — Fixed word-count windows (baseline)
  2. fixed_sentence   — Sentence boundaries, target N sentences per chunk
  3. paragraph        — Split on blank lines / paragraph breaks
  4. semantic         — Embedding-based split at semantic discontinuities
  5. recursive        — LangChain-style recursive character splitting
  6. sliding_window   — High-overlap sliding window for dense retrieval
  7. token_aware      — Split on token count (LLM-friendly)
  8. section_aware    — Header/section detection for structured docs
  9. code_aware       — Function/class boundary detection for code files
 10. table_intact     — Keep markdown/HTML tables as atomic chunks (D09)
 11. step_aware       — Split at numbered step boundaries (D19 procedural)

Decision engine:
  - Rule-based first: doc_type → best strategy (fast, no overhead)
  - Quality scoring: if rule score < threshold, trial top 2 candidates
    and pick the one with best self-consistency retrieval score.
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ChunkingResult:
    """Result of chunking optimization."""
    chunks: List[str]
    strategy: str            # name of chosen strategy
    chunk_count: int
    avg_chunk_words: float
    score: float             # 0.0 – 1.0 quality estimate
    reason: str


# ─── Rule-based strategy selection ────────────────────────────────────────────

# doc_type → ordered list of preferred strategies (first = best default)
_STRATEGY_PREFERENCE: Dict[str, List[str]] = {
    "academic":       ["section_aware", "paragraph", "fixed_word"],
    "legal":          ["paragraph", "section_aware", "fixed_word"],
    "medical":        ["paragraph", "fixed_sentence", "fixed_word"],
    "financial_doc":  ["section_aware", "paragraph", "fixed_word"],
    "narrative":      ["paragraph", "fixed_sentence", "fixed_word"],
    "code":           ["code_aware", "section_aware", "fixed_word"],
    "tabular":        ["fixed_word"],   # usually bypassed to SQL pipeline
    "mixed":          ["recursive", "paragraph", "fixed_word"],
}

_SUBTYPE_OVERRIDE: Dict[str, str] = {
    "faq":             "step_aware",
    "policy":          "section_aware",
    "research_paper":  "section_aware",
    "source_code":     "code_aware",
    "notebook":        "code_aware",
    "structured_data": "recursive",
    "procedural":      "step_aware",
    "manual":          "step_aware",
    "tutorial":        "step_aware",
    # D09: markdown files with embedded tables → preserve table structure intact
    "markdown_table":  "table_intact",
}


class ChunkingOptimizer:
    """
    Multi-strategy chunking engine with automatic strategy selection.

    Usage:
        optimizer = ChunkingOptimizer()
        result = optimizer.optimize(text, doc_type="academic", doc_subtype="research_paper")
        chunks = result.chunks  # best strategy selected automatically
    """

    def optimize(
        self,
        text: str,
        doc_type: str = "narrative",
        doc_subtype: str = "general",
        chunk_size: int = 512,
        overlap: int = 64,
        trial_scoring: bool = False,  # enable trial-and-score if True
    ) -> ChunkingResult:
        """
        Choose the best chunking strategy and return chunks.

        Args:
            text: Full document text.
            doc_type: Detected document type (from DocumentClassifier).
            doc_subtype: Document subtype.
            chunk_size: Target words per chunk (used by most strategies).
            overlap: Word overlap between consecutive chunks.
            trial_scoring: If True, run top-2 strategies and score them.

        Returns:
            ChunkingResult with the best chunks and metadata.
        """
        # 1. Rule-based selection
        strategy = self._select_strategy(doc_type, doc_subtype)
        candidates = _STRATEGY_PREFERENCE.get(doc_type, ["fixed_word"])

        if trial_scoring and len(candidates) > 1:
            # Run top-2 strategies and pick the better one
            results = []
            for s in candidates[:2]:
                chunks = self._run_strategy(s, text, chunk_size, overlap)
                score = self._score_chunks(chunks, text)
                results.append((s, chunks, score))
            results.sort(key=lambda x: x[2], reverse=True)
            best_strategy, best_chunks, best_score = results[0]
        else:
            best_chunks = self._run_strategy(strategy, text, chunk_size, overlap)
            best_score = self._score_chunks(best_chunks, text)
            best_strategy = strategy

        # Ensure non-empty result
        if not best_chunks:
            best_chunks = self._fixed_word(text, chunk_size, overlap)
            best_strategy = "fixed_word"
            best_score = 0.5

        word_counts = [len(c.split()) for c in best_chunks]
        avg_words = sum(word_counts) / len(word_counts) if word_counts else 0

        logger.info(
            "ChunkingOptimizer: doc_type=%s subtype=%s strategy=%s chunks=%d avg_words=%.0f score=%.2f",
            doc_type, doc_subtype, best_strategy, len(best_chunks), avg_words, best_score,
        )

        return ChunkingResult(
            chunks=best_chunks,
            strategy=best_strategy,
            chunk_count=len(best_chunks),
            avg_chunk_words=avg_words,
            score=best_score,
            reason=f"Strategy '{best_strategy}' selected for {doc_type}/{doc_subtype}",
        )

    def chunk_with_strategy(
        self,
        text: str,
        strategy: str,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> List[str]:
        """Directly run a named strategy. For external callers."""
        return self._run_strategy(strategy, text, chunk_size, overlap)

    # ── Strategy selection ─────────────────────────────────────────────────────

    @staticmethod
    def _select_strategy(doc_type: str, doc_subtype: str) -> str:
        """Rule-based: subtype override → type default → fallback."""
        if doc_subtype in _SUBTYPE_OVERRIDE:
            return _SUBTYPE_OVERRIDE[doc_subtype]
        prefs = _STRATEGY_PREFERENCE.get(doc_type, ["fixed_word"])
        return prefs[0]

    def _run_strategy(self, strategy: str, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Dispatch to the appropriate strategy implementation."""
        dispatch = {
            "fixed_word":      lambda: self._fixed_word(text, chunk_size, overlap),
            "fixed_sentence":  lambda: self._fixed_sentence(text, chunk_size),
            "paragraph":       lambda: self._paragraph(text, chunk_size),
            "semantic":        lambda: self._semantic(text, chunk_size, overlap),
            "recursive":       lambda: self._recursive(text, chunk_size, overlap),
            "sliding_window":  lambda: self._sliding_window(text, chunk_size, overlap),
            "token_aware":     lambda: self._token_aware(text, chunk_size, overlap),
            "section_aware":   lambda: self._section_aware(text, chunk_size),
            "code_aware":      lambda: self._code_aware(text, chunk_size),
            "table_intact":    lambda: self._table_intact(text, chunk_size),
            "step_aware":      lambda: self._step_aware(text, chunk_size),
        }
        fn = dispatch.get(strategy, dispatch["fixed_word"])
        try:
            chunks = fn()
            return [c.strip() for c in chunks if c.strip()]
        except Exception as e:
            logger.warning("Strategy '%s' failed: %s — falling back to fixed_word", strategy, e)
            return self._fixed_word(text, chunk_size, overlap)

    # ── 9 Strategy implementations ─────────────────────────────────────────────

    @staticmethod
    def _fixed_word(text: str, chunk_size: int, overlap: int) -> List[str]:
        """Strategy 1: Fixed word-count windows with overlap."""
        words = text.split()
        if not words:
            return []
        step = max(chunk_size - overlap, 1)
        chunks = []
        for i in range(0, len(words), step):
            chunk = " ".join(words[i: i + chunk_size])
            chunks.append(chunk)
            if i + chunk_size >= len(words):
                break
        return chunks

    @staticmethod
    def _fixed_sentence(text: str, chunk_size: int) -> List[str]:
        """Strategy 2: Sentence-boundary splitting, grouping N sentences per chunk."""
        # Split on sentence-ending punctuation
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return [text]

        chunks = []
        current: List[str] = []
        current_words = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if current_words + sent_words > chunk_size and current:
                chunks.append(" ".join(current))
                # Carry over last sentence for context
                current = [current[-1]] if current else []
                current_words = len(current[0].split()) if current else 0
            current.append(sent)
            current_words += sent_words

        if current:
            chunks.append(" ".join(current))
        return chunks

    @staticmethod
    def _paragraph(text: str, chunk_size: int) -> List[str]:
        """Strategy 3: Paragraph-based splitting (split on blank lines)."""
        paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        if not paragraphs:
            return [text]

        chunks = []
        current_parts: List[str] = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())
            if para_words > chunk_size * 2:
                # Very long paragraph — split by sentences inside it
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_words = 0
                # Sub-split the long paragraph
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sub_chunk: List[str] = []
                sub_words = 0
                for sent in sentences:
                    sw = len(sent.split())
                    if sub_words + sw > chunk_size and sub_chunk:
                        chunks.append(" ".join(sub_chunk))
                        sub_chunk = [sub_chunk[-1]] if sub_chunk else []
                        sub_words = len(sub_chunk[0].split()) if sub_chunk else 0
                    sub_chunk.append(sent)
                    sub_words += sw
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
            elif current_words + para_words > chunk_size and current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = [para]
                current_words = para_words
            else:
                current_parts.append(para)
                current_words += para_words

        if current_parts:
            chunks.append("\n\n".join(current_parts))
        return chunks

    @staticmethod
    def _semantic(text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        Strategy 4: Semantic splitting via embedding cosine-similarity.
        Falls back to paragraph splitting if embeddings unavailable.
        """
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            model = SentenceTransformer("all-MiniLM-L6-v2")

            sentences = re.split(r"(?<=[.!?])\s+", text.strip())
            sentences = [s.strip() for s in sentences if len(s.split()) >= 3]
            if len(sentences) < 4:
                return ChunkingOptimizer._fixed_word(text, chunk_size, overlap)

            embeddings = model.encode(sentences, show_progress_bar=False)
            # Compute cosine similarity between consecutive sentences
            splits = [0]
            for i in range(1, len(sentences) - 1):
                sim = float(np.dot(embeddings[i - 1], embeddings[i]) /
                            (np.linalg.norm(embeddings[i - 1]) * np.linalg.norm(embeddings[i]) + 1e-10))
                if sim < 0.75:  # semantic break
                    splits.append(i)
            splits.append(len(sentences))

            chunks = []
            for si in range(len(splits) - 1):
                group = sentences[splits[si]: splits[si + 1]]
                chunk = " ".join(group)
                if len(chunk.split()) > chunk_size:
                    # Sub-split large semantic chunks
                    chunks.extend(ChunkingOptimizer._fixed_word(chunk, chunk_size, overlap))
                else:
                    chunks.append(chunk)
            return chunks
        except ImportError:
            return ChunkingOptimizer._paragraph(text, chunk_size)

    @staticmethod
    def _recursive(text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        Strategy 5: Recursive character splitting (LangChain-style).
        Tries progressively finer separators until chunks fit target size.
        """
        separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]
        char_limit = chunk_size * 6  # ~6 chars per word on average

        def _split(text: str, seps: List[str]) -> List[str]:
            if not seps or len(text) <= char_limit:
                return [text]
            sep = seps[0]
            parts = text.split(sep)
            result = []
            current = ""
            for part in parts:
                candidate = current + sep + part if current else part
                if len(candidate) <= char_limit:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    if len(part) > char_limit:
                        result.extend(_split(part, seps[1:]))
                        current = ""
                    else:
                        current = part
            if current:
                result.append(current)
            return result

        raw = _split(text, separators)
        # Merge tiny chunks (< 20% of target)
        min_words = int(chunk_size * 0.2)
        merged = []
        buf = ""
        for chunk in raw:
            if len((buf + " " + chunk).split()) <= chunk_size:
                buf = (buf + " " + chunk).strip()
            else:
                if buf:
                    merged.append(buf)
                buf = chunk
        if buf:
            merged.append(buf)
        return merged

    @staticmethod
    def _sliding_window(text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        Strategy 6: High-overlap sliding window.
        Uses 50% overlap for dense retrieval on Q&A / FAQ content.
        """
        high_overlap = max(chunk_size // 2, overlap)
        return ChunkingOptimizer._fixed_word(text, chunk_size, high_overlap)

    @staticmethod
    def _token_aware(text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        Strategy 7: Token-count-aware splitting.
        Estimates tokens as words × 1.3 to stay under LLM context limits.
        """
        token_ratio = 1.3  # rough word-to-token ratio
        word_limit = int(chunk_size / token_ratio)
        return ChunkingOptimizer._fixed_word(text, word_limit, overlap)

    @staticmethod
    def _section_aware(text: str, chunk_size: int) -> List[str]:
        """
        Strategy 8: Section/heading-aware splitting.
        Splits on markdown headers or ALL-CAPS lines (common in PDFs).
        """
        # Matches: ## Heading, SECTION 1, 1. Introduction, etc.
        section_re = re.compile(
            r"(?m)^(?:"
            r"#{1,4}\s+.+|"           # Markdown headings
            r"[A-Z][A-Z\s\d\-:]{5,}|"  # ALL-CAPS lines
            r"\d+\.\s+[A-Z].{3,}|"   # 1. Title style
            r"Chapter\s+\d+"          # Chapter N
            r")$"
        )

        positions = [m.start() for m in section_re.finditer(text)]
        if len(positions) < 2:
            # Fall back to paragraph splitting
            return ChunkingOptimizer._paragraph(text, chunk_size)

        sections = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            sections.append(text[pos:end].strip())

        chunks = []
        for section in sections:
            if len(section.split()) <= chunk_size:
                chunks.append(section)
            else:
                chunks.extend(ChunkingOptimizer._paragraph(section, chunk_size))
        return chunks

    @staticmethod
    def _code_aware(text: str, chunk_size: int) -> List[str]:
        """
        Strategy 9: Code-aware splitting.
        Splits at function/class boundaries (Python, JS, Java, etc.)
        """
        # Detect function/class boundaries
        func_re = re.compile(
            r"(?m)^(?:"
            r"(?:def|class|async def)\s+\w+|"  # Python
            r"function\s+\w+|"                  # JS/TS
            r"(?:public|private|protected|static)?\s+\w+\s+\w+\s*\(|"  # Java/C++
            r"func\s+\w+|"                      # Go/Swift
            r"fn\s+\w+"                          # Rust
            r")"
        )

        positions = [m.start() for m in func_re.finditer(text)]

        if len(positions) < 2:
            # Fallback to fixed-word for code without clear boundaries
            return ChunkingOptimizer._fixed_word(text, chunk_size, chunk_size // 4)

        chunks = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            block = text[pos:end].strip()
            if not block:
                continue
            if len(block.split()) <= chunk_size:
                chunks.append(block)
            else:
                # Large function — split by lines
                lines = block.split("\n")
                sub = []
                sub_words = 0
                for line in lines:
                    lw = len(line.split())
                    if sub_words + lw > chunk_size and sub:
                        chunks.append("\n".join(sub))
                        sub = []
                        sub_words = 0
                    sub.append(line)
                    sub_words += lw
                if sub:
                    chunks.append("\n".join(sub))

        # Include any preamble (imports, comments) before first function
        if positions[0] > 50:
            preamble = text[:positions[0]].strip()
            if preamble:
                chunks.insert(0, preamble[:chunk_size * 5])  # cap preamble

        return chunks

    @staticmethod
    def _table_intact(text: str, chunk_size: int) -> List[str]:
        """
        Strategy 10: Table-intact splitting.

        Markdown tables (|col|col| rows) and HTML <table>…</table> blocks are
        treated as atomic units — no row is ever split across chunks.
        Text between tables is chunked at paragraph boundaries.

        Addresses dataset type D09 (Markdown Tables) where splitting a table
        row-by-row loses the column context and destroys structure.
        """
        chunks: List[str] = []

        # Detect markdown table blocks: consecutive lines starting with |
        # Also detect HTML <table> blocks
        markdown_table_re = re.compile(
            r'(?:(?:[ \t]*\|[^\n]*\|[ \t]*\n)+(?:[ \t]*\|[^\n]*\|[ \t]*\n?)+)',
        )
        html_table_re = re.compile(
            r'<table[\s\S]*?</table>',
            re.IGNORECASE,
        )

        # Collect all table spans sorted by start position
        table_spans: List[tuple] = []
        for m in markdown_table_re.finditer(text):
            # Require at least 2 rows (header + separator or data)
            rows = [r for r in m.group(0).strip().split('\n') if r.strip()]
            if len(rows) >= 2:
                table_spans.append((m.start(), m.end(), m.group(0).strip()))
        for m in html_table_re.finditer(text):
            table_spans.append((m.start(), m.end(), m.group(0).strip()))

        # Sort by position, resolve overlaps
        table_spans.sort(key=lambda x: x[0])
        merged_spans: List[tuple] = []
        for span in table_spans:
            if merged_spans and span[0] < merged_spans[-1][1]:
                # Overlapping — skip (already covered)
                continue
            merged_spans.append(span)

        # Build chunks: non-table text → paragraph split, tables → single chunk
        cursor = 0
        for start, end, table_text in merged_spans:
            # Text before the table
            before = text[cursor:start].strip()
            if before:
                chunks.extend(ChunkingOptimizer._paragraph(before, chunk_size))
            # The table itself — kept whole; if huge, log a warning but don't split
            if table_text:
                table_words = len(table_text.split())
                if table_words > chunk_size * 4:
                    logger.debug(
                        "table_intact: table has %d words (> 4× chunk_size=%d), kept whole",
                        table_words, chunk_size,
                    )
                chunks.append(table_text)
            cursor = end

        # Remaining text after last table
        tail = text[cursor:].strip()
        if tail:
            chunks.extend(ChunkingOptimizer._paragraph(tail, chunk_size))

        # Fallback if no tables were found
        if not chunks:
            return ChunkingOptimizer._paragraph(text, chunk_size)

        return chunks

    @staticmethod
    def _step_aware(text: str, chunk_size: int) -> List[str]:
        """
        Strategy 11: Step-aware splitting for procedural documents.

        Splits at numbered step boundaries:
          "1. ...", "Step 1:", "Step 1 —", "(1) ...", "1) ..."

        Each step becomes one chunk. Short consecutive steps (< 30 words each)
        are merged to avoid tiny chunks. Long steps are sub-split by sentences.

        Addresses dataset type D19 (Procedural Instructions) where step order
        is lost when steps span chunk boundaries.
        """
        # Detect step markers: must be at start of a line (possibly after whitespace)
        step_re = re.compile(
            r'(?m)(?:^|\n)[ \t]*(?:'
            r'Step\s+\d+\s*[:\.\-\u2014]|'   # "Step 1:", "Step 1 —"
            r'\d{1,3}[\.\)]\s+(?=\S)|'         # "1. text" or "1) text"
            r'\(\d{1,3}\)\s+'                  # "(1) text"
            r')',
            re.IGNORECASE,
        )

        matches = list(step_re.finditer(text))
        if len(matches) < 2:
            # Not a procedural doc — fall back to paragraph
            return ChunkingOptimizer._paragraph(text, chunk_size)

        # Extract preamble (text before first step marker)
        raw_chunks: List[str] = []
        preamble = text[:matches[0].start()].strip()
        if preamble:
            raw_chunks.append(preamble)

        # Extract each step's text
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            step_text = text[start:end].strip()
            if step_text:
                raw_chunks.append(step_text)

        # Merge short consecutive steps, sub-split long ones
        MIN_STEP_WORDS = 30
        chunks: List[str] = []
        buffer = ""
        buffer_words = 0

        for chunk in raw_chunks:
            words = len(chunk.split())
            if words > chunk_size:
                # Long step — flush buffer first, then sub-split
                if buffer:
                    chunks.append(buffer.strip())
                    buffer = ""
                    buffer_words = 0
                chunks.extend(ChunkingOptimizer._fixed_sentence(chunk, chunk_size))
            elif buffer_words + words < MIN_STEP_WORDS:
                # Too short — accumulate
                buffer = (buffer + "\n\n" + chunk).strip() if buffer else chunk
                buffer_words += words
            else:
                if buffer:
                    chunks.append(buffer.strip())
                buffer = chunk
                buffer_words = words

        if buffer:
            chunks.append(buffer.strip())

        return [c for c in chunks if c.strip()] or ChunkingOptimizer._paragraph(text, chunk_size)

    # ── Quality scoring ────────────────────────────────────────────────────────

    @staticmethod
    def _score_chunks(chunks: List[str], full_text: str) -> float:
        """
        Heuristic quality score for a chunking result.

        Criteria:
        - Coverage: total words in chunks vs original
        - Uniformity: std-dev of chunk sizes (lower = better)
        - Avg chunk length: penalise if too short (<50 words) or too long (>1500 words)
        """
        if not chunks:
            return 0.0

        import math

        total_original = len(full_text.split())
        total_chunked = sum(len(c.split()) for c in chunks)
        coverage = min(total_chunked / max(total_original, 1), 1.0)

        sizes = [len(c.split()) for c in chunks]
        avg = sum(sizes) / len(sizes)
        variance = sum((s - avg) ** 2 for s in sizes) / len(sizes)
        std = math.sqrt(variance)
        uniformity = max(0.0, 1.0 - std / max(avg, 1))

        # Penalise extremes in average chunk size
        if avg < 30:
            length_score = 0.3
        elif avg < 80:
            length_score = 0.7
        elif avg <= 600:
            length_score = 1.0
        elif avg <= 1200:
            length_score = 0.8
        else:
            length_score = 0.5

        score = (coverage * 0.30) + (uniformity * 0.40) + (length_score * 0.30)
        return round(score, 3)
