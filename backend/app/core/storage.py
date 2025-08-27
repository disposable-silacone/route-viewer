from __future__ import annotations

from typing import Protocol, BinaryIO, runtime_checkable
from pathlib import Path
import zipfile


@runtime_checkable
class StorageProvider(Protocol):
    def list_entries(self, uri: str) -> list[str]:
        ...

    def open_binary(self, uri: str) -> BinaryIO:
        ...

    def is_archive(self, uri: str) -> bool:
        ...

    def join(self, *parts: str) -> str:
        ...


class LocalStorageProvider:
    """Local filesystem storage provider.

    Accepts absolute paths or file:// URIs for Phase 1.
    """

    def _to_path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(uri[7:])
        return Path(uri)

    def list_entries(self, uri: str) -> list[str]:
        path = self._to_path(uri)
        if not path.exists():
            return []
        if path.is_file():
            return [str(path)]
        return [str(p) for p in path.rglob("*")]

    def open_binary(self, uri: str) -> BinaryIO:
        return self._to_path(uri).open("rb")

    def is_archive(self, uri: str) -> bool:
        try:
            return zipfile.is_zipfile(self._to_path(uri))
        except Exception:
            return False

    def join(self, *parts: str) -> str:
        return str(Path(*parts))


