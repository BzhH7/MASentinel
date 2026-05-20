from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FileRecord:
    mtime_ns: int
    size: int


class FilesystemMonitor:
    def __init__(self, allowed_roots: list[Path], watch_roots: list[Path] | None = None, max_files: int = 10_000) -> None:
        self.allowed_roots = [_resolve(root) for root in allowed_roots]
        self.watch_roots = [_resolve(root) for root in (watch_roots or allowed_roots)]
        self.max_files = max_files
        self.before: dict[str, FileRecord] = {}

    def snapshot_before(self) -> None:
        self.before = self._snapshot()

    def snapshot_after(self) -> dict[str, Any]:
        after = self._snapshot()
        before_keys = set(self.before)
        after_keys = set(after)
        created = sorted(after_keys - before_keys)
        modified = sorted(
            path
            for path in (after_keys & before_keys)
            if after[path].mtime_ns != self.before[path].mtime_ns or after[path].size != self.before[path].size
        )
        outside = sorted(path for path in created + modified if not self._inside_allowed(Path(path)))
        return {
            "created_files": created[:200],
            "modified_files": modified[:200],
            "outside_root_writes": outside[:200],
            "truncated": len(created) > 200 or len(modified) > 200,
            "allowed_roots": [str(root) for root in self.allowed_roots],
            "watch_roots": [str(root) for root in self.watch_roots],
        }

    def _snapshot(self) -> dict[str, FileRecord]:
        result: dict[str, FileRecord] = {}
        count = 0
        for root in self.watch_roots:
            if not root.exists():
                continue
            if root.is_file():
                self._add_file(root, result)
                continue
            for path in root.rglob("*"):
                if count >= self.max_files:
                    return result
                if not path.is_file() or _skip_path(path):
                    continue
                self._add_file(path, result)
                count += 1
        return result

    def _add_file(self, path: Path, result: dict[str, FileRecord]) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        result[str(_resolve(path))] = FileRecord(mtime_ns=stat.st_mtime_ns, size=stat.st_size)

    def _inside_allowed(self, path: Path) -> bool:
        resolved = _resolve(path)
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _skip_path(path: Path) -> bool:
    skip_parts = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".cache",
        ".masentinel_fixture",
        "node_modules",
        "site-packages",
    }
    return any(part in skip_parts for part in path.parts)
