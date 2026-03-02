"""
Language Detector for Intelligent Auto-RAG.

Detects the primary language of a document so the system can
automatically switch to the appropriate multilingual embedding model.

Strategy:
  1. Use langdetect (pip install langdetect) — fast, no API needed.
  2. Fall back to character-frequency heuristics (CJK, Arabic, Cyrillic, etc.)
  3. Default to English if detection fails.

Embedding model routing:
  - English only        → use the configured default embedding model
  - Multilingual        → use 'intfloat/multilingual-e5-base' (sentence-transformers)
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Languages that are natively well-served by English-only dense models
_ENGLISH_LIKE = {"en", "en-US", "en-GB"}

# Embedding model to use for non-English / multilingual content
_MULTILINGUAL_MODEL = "intfloat/multilingual-e5-base"

# Script detection regexes (used as fallback when langdetect unavailable)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")


@dataclass
class LanguageResult:
    """Result of language detection."""
    language: str          # ISO 639-1 code, e.g. "en", "zh", "ar"
    confidence: float      # 0.0 – 1.0
    is_multilingual: bool  # True if non-English content detected
    embedding_hint: str    # embedding model to use
    script: str            # "latin", "cjk", "arabic", "cyrillic", "devanagari", "thai", "unknown"


class LanguageDetector:
    """
    Detects language of text and recommends the appropriate embedding model.

    Usage:
        detector = LanguageDetector()
        result = detector.detect("Bonjour le monde")
        # result.language == "fr"
        # result.is_multilingual == True
        # result.embedding_hint == "intfloat/multilingual-e5-base"
    """

    def detect(self, text: str) -> LanguageResult:
        """
        Detect language from text sample.

        Args:
            text: Any text (first 2000 chars used for speed).

        Returns:
            LanguageResult with language code, confidence, and embedding hint.
        """
        sample = text[:2000].strip()
        if not sample:
            return self._default_english()

        # 1. Try langdetect
        lang, conf = self._try_langdetect(sample)

        # 2. Fallback: script-based heuristic
        if lang is None:
            lang, conf = self._script_heuristic(sample)

        is_multi = lang not in _ENGLISH_LIKE
        embedding = _MULTILINGUAL_MODEL if is_multi else "default"
        script = self._detect_script(sample)

        logger.info(
            "LanguageDetector: lang=%s conf=%.2f script=%s multilingual=%s",
            lang, conf, script, is_multi,
        )

        return LanguageResult(
            language=lang,
            confidence=conf,
            is_multilingual=is_multi,
            embedding_hint=embedding,
            script=script,
        )

    def detect_from_file(self, file_path: str) -> LanguageResult:
        """
        Detect language from a file's text content (reads first 5KB).
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(5000)
            return self.detect(sample)
        except Exception as e:
            logger.debug("Language detection from file failed: %s", e)
            return self._default_english()

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _try_langdetect(text: str):
        """Try langdetect library. Returns (lang_code, confidence) or (None, 0.0)."""
        try:
            from langdetect import detect_langs
            results = detect_langs(text)
            if results:
                top = results[0]
                return top.lang, round(top.prob, 3)
        except ImportError:
            logger.debug("langdetect not installed; using script heuristic")
        except Exception as e:
            logger.debug("langdetect failed: %s", e)
        return None, 0.0

    @staticmethod
    def _script_heuristic(text: str):
        """Heuristic language detection via script character frequency."""
        total = len(text)
        if total == 0:
            return "en", 0.5

        cjk_ratio = len(_CJK_RE.findall(text)) / total
        arabic_ratio = len(_ARABIC_RE.findall(text)) / total
        cyrillic_ratio = len(_CYRILLIC_RE.findall(text)) / total
        devanagari_ratio = len(_DEVANAGARI_RE.findall(text)) / total
        thai_ratio = len(_THAI_RE.findall(text)) / total

        candidates = [
            (cjk_ratio, "zh"),
            (arabic_ratio, "ar"),
            (cyrillic_ratio, "ru"),
            (devanagari_ratio, "hi"),
            (thai_ratio, "th"),
        ]
        best_ratio, best_lang = max(candidates, key=lambda x: x[0])

        if best_ratio > 0.05:  # >5% foreign script → non-English
            return best_lang, min(best_ratio * 3, 0.90)

        return "en", 0.70  # Default to English

    @staticmethod
    def _detect_script(text: str) -> str:
        """Determine dominant writing script."""
        sample = text[:500]
        if _CJK_RE.search(sample):
            return "cjk"
        if _ARABIC_RE.search(sample):
            return "arabic"
        if _CYRILLIC_RE.search(sample):
            return "cyrillic"
        if _DEVANAGARI_RE.search(sample):
            return "devanagari"
        if _THAI_RE.search(sample):
            return "thai"
        return "latin"

    @staticmethod
    def _default_english() -> LanguageResult:
        return LanguageResult(
            language="en",
            confidence=0.5,
            is_multilingual=False,
            embedding_hint="default",
            script="latin",
        )
