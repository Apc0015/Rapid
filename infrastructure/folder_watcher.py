"""
Local folder watcher — monitors a directory path for new/changed files
and automatically ingests them into the RAPID knowledge base.

Uses asyncio polling (no external dependencies like watchdog).
Each watcher runs as a background task inside the FastAPI process.

Usage:
  manager = get_folder_watcher()
  watcher_id = await manager.add_watcher(
      path="/mnt/shared/company-docs",
      dept_tag="hr",
      interval_seconds=60,
  )
  manager.start_all()   # called once at app startup
  await manager.stop_watcher(watcher_id)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rapid.folder_watcher")

# File types the doc_master can handle
_WATCHABLE_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv", ".json",
    ".py", ".js", ".ts", ".yaml", ".yml", ".html",
}

_DEFAULT_INTERVAL = 60   # seconds between polls


@dataclass
class WatcherConfig:
    watcher_id:       str
    path:             str
    dept_tag:         Optional[str]
    project_id:       Optional[str]
    interval_seconds: int
    extensions:       set[str]
    created_by:       str          # user_id of admin who created it
    created_at:       float = field(default_factory=time.time)
    last_scan:        float = 0.0
    files_seen:       int = 0
    chunks_ingested:  int = 0
    errors:           int = 0
    active:           bool = True


class FolderWatcherManager:
    """
    Manages a collection of local-folder watchers.
    Each watcher is an asyncio task that polls a directory at a fixed interval.
    """

    def __init__(self):
        self._watchers: dict[str, WatcherConfig] = {}
        self._tasks:    dict[str, asyncio.Task]  = {}
        self._known:    dict[str, float]          = {}  # path → mtime cache

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_watcher(
        self,
        path: str,
        dept_tag: Optional[str] = None,
        project_id: Optional[str] = None,
        interval_seconds: int = _DEFAULT_INTERVAL,
        extensions: Optional[list[str]] = None,
        created_by: str = "admin",
    ) -> WatcherConfig:
        """Register a new folder watcher (does not start it immediately)."""
        if not os.path.isdir(path):
            raise ValueError(f"Path does not exist or is not a directory: {path}")
        if not dept_tag and not project_id:
            raise ValueError("Supply either dept_tag or project_id")

        watcher_id = f"fw_{uuid.uuid4().hex[:8]}"
        cfg = WatcherConfig(
            watcher_id=watcher_id,
            path=path,
            dept_tag=dept_tag,
            project_id=project_id,
            interval_seconds=max(10, interval_seconds),
            extensions=set(extensions) if extensions else _WATCHABLE_EXTENSIONS,
            created_by=created_by,
        )
        self._watchers[watcher_id] = cfg
        logger.info(f"[watcher] Registered watcher {watcher_id} → {path}")
        return cfg

    def start_watcher(self, watcher_id: str) -> None:
        """Start the background polling task for a watcher."""
        cfg = self._watchers.get(watcher_id)
        if not cfg:
            raise KeyError(f"Watcher {watcher_id} not found")
        if watcher_id in self._tasks and not self._tasks[watcher_id].done():
            logger.debug(f"[watcher] {watcher_id} already running")
            return
        task = asyncio.create_task(self._poll_loop(cfg), name=f"watcher-{watcher_id}")
        self._tasks[watcher_id] = task
        logger.info(f"[watcher] Started {watcher_id} (interval={cfg.interval_seconds}s path={cfg.path})")

    def start_all(self) -> None:
        """Start all registered watchers (called at app startup)."""
        for wid in list(self._watchers.keys()):
            if self._watchers[wid].active:
                self.start_watcher(wid)

    async def stop_watcher(self, watcher_id: str) -> None:
        """Stop and remove a watcher."""
        if watcher_id in self._tasks:
            self._tasks[watcher_id].cancel()
            try:
                await self._tasks[watcher_id]
            except asyncio.CancelledError:
                pass
            del self._tasks[watcher_id]
        if watcher_id in self._watchers:
            self._watchers[watcher_id].active = False
        logger.info(f"[watcher] Stopped {watcher_id}")

    async def stop_all(self) -> None:
        """Stop all watchers gracefully (called at app shutdown)."""
        for wid in list(self._tasks.keys()):
            await self.stop_watcher(wid)

    def list_watchers(self) -> list[dict]:
        return [self._watcher_to_dict(cfg) for cfg in self._watchers.values()]

    def get_watcher(self, watcher_id: str) -> Optional[dict]:
        cfg = self._watchers.get(watcher_id)
        return self._watcher_to_dict(cfg) if cfg else None

    async def trigger_scan(self, watcher_id: str) -> dict:
        """Force an immediate scan outside the regular interval."""
        cfg = self._watchers.get(watcher_id)
        if not cfg:
            raise KeyError(f"Watcher {watcher_id} not found")
        return await self._scan_directory(cfg)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _poll_loop(self, cfg: WatcherConfig) -> None:
        """Background coroutine: sleep → scan → repeat."""
        logger.info(f"[watcher] Poll loop started for {cfg.watcher_id}")
        while cfg.active:
            try:
                await self._scan_directory(cfg)
            except Exception as exc:
                cfg.errors += 1
                logger.error(f"[watcher] Scan error for {cfg.watcher_id}: {exc}")
            await asyncio.sleep(cfg.interval_seconds)

    async def _scan_directory(self, cfg: WatcherConfig) -> dict:
        """
        Walk the directory, find new/modified files, ingest them.
        Tracks seen files by (path, mtime) so already-ingested files are skipped.
        """
        cfg.last_scan = time.time()
        new_files = 0
        new_chunks = 0
        errors = 0

        try:
            entries = list(Path(cfg.path).rglob("*"))
        except PermissionError as e:
            logger.error(f"[watcher] Permission error reading {cfg.path}: {e}")
            return {"new_files": 0, "new_chunks": 0}

        from infrastructure.doc_master import get_doc_master
        doc = get_doc_master()

        for entry in entries:
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in cfg.extensions:
                continue

            file_key = str(entry)
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue

            if self._known.get(file_key) == mtime:
                continue   # already ingested this version

            try:
                tag = cfg.dept_tag or f"project_{cfg.project_id}"
                chunks = await doc.ingest_document(str(entry), tag)
                self._known[file_key] = mtime
                new_files += 1
                new_chunks += chunks
                cfg.files_seen += 1
                cfg.chunks_ingested += chunks
                logger.info(f"[watcher] Auto-ingested {entry.name} → {chunks} chunks (tag={tag})")
            except Exception as exc:
                errors += 1
                cfg.errors += 1
                logger.warning(f"[watcher] Failed to ingest {entry.name}: {exc}")

        if new_files:
            logger.info(
                f"[watcher] {cfg.watcher_id} scan complete: "
                f"{new_files} new files, {new_chunks} chunks"
            )
        return {"new_files": new_files, "new_chunks": new_chunks, "errors": errors}

    @staticmethod
    def _watcher_to_dict(cfg: WatcherConfig) -> dict:
        running = False
        return {
            "watcher_id":       cfg.watcher_id,
            "path":             cfg.path,
            "dept_tag":         cfg.dept_tag,
            "project_id":       cfg.project_id,
            "interval_seconds": cfg.interval_seconds,
            "extensions":       sorted(cfg.extensions),
            "created_by":       cfg.created_by,
            "created_at":       cfg.created_at,
            "last_scan":        cfg.last_scan,
            "files_seen":       cfg.files_seen,
            "chunks_ingested":  cfg.chunks_ingested,
            "errors":           cfg.errors,
            "active":           cfg.active,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[FolderWatcherManager] = None


def get_folder_watcher() -> FolderWatcherManager:
    global _manager
    if _manager is None:
        _manager = FolderWatcherManager()
    return _manager
