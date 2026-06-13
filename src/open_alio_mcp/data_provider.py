# -*- coding: utf-8 -*-
"""데이터 공급 계층 — Tool/Store는 이 모듈을 통해서만 정적 데이터를 읽는다.

계층 구조:
    Tool Layer (server.py)
        ↓
    Repository Layer (metrics_store · disclosure_store · …)
        ↓
    Data Provider (이 모듈)
        ↓
    LocalDirProvider(data/) 또는 SqliteSnapshotProvider(alio_snapshot.db)

데이터 위치 해석 순서:
1. OPEN_ALIO_DATA_DIR     — 디렉터리 직접 지정 (개발·사내 데이터 교체용)
2. OPEN_ALIO_SNAPSHOT_PATH — SQLite 스냅샷 파일 직접 지정
3. 소스 체크아웃의 data/   — 저장소에서 직접 실행하는 개발 모드
4. 사용자 데이터 디렉터리의 alio_snapshot.db — 없으면 GitHub Release에서 자동 다운로드

향후 PostgreSQL·사내 DW 등으로 교체할 때는 DataProvider 구현체만 추가하면 되고
Tool API와 Repository 코드는 변경하지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import zlib
from pathlib import Path
from typing import Any

from .snapshot import ensure_snapshot, read_meta

log = logging.getLogger("open-alio-mcp.data")


class DataProvider:
    """정적 데이터 읽기 인터페이스. 경로는 data/ 기준 POSIX 상대경로."""

    def exists(self, rel: str) -> bool:
        raise NotImplementedError

    def read_bytes(self, rel: str) -> bytes:
        """없으면 FileNotFoundError."""
        raise NotImplementedError

    def list_paths(self, prefix: str) -> list[str]:
        raise NotImplementedError

    def describe(self) -> dict:
        raise NotImplementedError

    # 공통 헬퍼
    def read_text(self, rel: str) -> str:
        return self.read_bytes(rel).decode("utf-8")

    def read_json(self, rel: str) -> Any:
        return json.loads(self.read_text(rel))

    def read_json_or_none(self, rel: str) -> Any | None:
        try:
            return self.read_json(rel)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None


class LocalDirProvider(DataProvider):
    """저장소 data/ 디렉터리(또는 OPEN_ALIO_DATA_DIR) 직접 읽기."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _path(self, rel: str) -> Path:
        path = (self.base_dir / rel).resolve()
        if not str(path).startswith(str(self.base_dir.resolve())):
            raise FileNotFoundError(rel)  # 디렉터리 탈출 방지
        return path

    def exists(self, rel: str) -> bool:
        return self._path(rel).is_file()

    def read_bytes(self, rel: str) -> bytes:
        return self._path(rel).read_bytes()

    def list_paths(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self.base_dir
        if not base.is_dir():
            return []
        return sorted(
            p.relative_to(self.base_dir).as_posix() for p in base.rglob("*.json") if p.is_file()
        )

    def describe(self) -> dict:
        return {"mode": "local-dir", "location": str(self.base_dir)}


class SqliteSnapshotProvider(DataProvider):
    """배포 스냅샷(alio_snapshot.db) 읽기 — 문서는 zlib 압축 저장."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = threading.local()  # FastMCP 멀티스레드 대비 연결 분리

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
            self._local.conn = conn
        return conn

    def exists(self, rel: str) -> bool:
        row = self._conn().execute("SELECT 1 FROM docs WHERE path = ?", (rel,)).fetchone()
        return row is not None

    def read_bytes(self, rel: str) -> bytes:
        row = self._conn().execute("SELECT content FROM docs WHERE path = ?", (rel,)).fetchone()
        if row is None:
            raise FileNotFoundError(rel)
        return zlib.decompress(row[0])

    def list_paths(self, prefix: str) -> list[str]:
        rows = self._conn().execute(
            "SELECT path FROM docs WHERE path LIKE ? ORDER BY path", (prefix + "%",)
        )
        return [r[0] for r in rows]

    def describe(self) -> dict:
        try:
            meta = read_meta(self.db_path)
        except sqlite3.Error:
            meta = {}
        return {
            "mode": "sqlite-snapshot",
            "location": str(self.db_path),
            "snapshot_built_at": meta.get("built_at"),
            "snapshot_doc_count": meta.get("doc_count"),
        }


_provider: DataProvider | None = None
_provider_lock = threading.Lock()


def _repo_data_dir() -> Path | None:
    """소스 체크아웃에서 실행 중이면 저장소의 data/ 경로 반환."""
    candidate = Path(__file__).resolve().parents[2] / "data"
    if (candidate / "institutions.json").is_file():
        return candidate
    return None


def _resolve_provider() -> DataProvider:
    env_dir = os.environ.get("OPEN_ALIO_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
        if not base.is_dir():
            raise FileNotFoundError(f"OPEN_ALIO_DATA_DIR가 디렉터리가 아닙니다: {base}")
        return LocalDirProvider(base)

    env_snapshot = os.environ.get("OPEN_ALIO_SNAPSHOT_PATH")
    if env_snapshot:
        return SqliteSnapshotProvider(ensure_snapshot(Path(env_snapshot)))

    repo_dir = _repo_data_dir()
    if repo_dir is not None:
        return LocalDirProvider(repo_dir)

    return SqliteSnapshotProvider(ensure_snapshot())


def get_provider() -> DataProvider:
    """현재 데이터 공급자 (최초 호출 시 해석 — 필요하면 스냅샷 자동 다운로드)."""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = _resolve_provider()
                log.info("데이터 공급자: %s", _provider.describe())
    return _provider


def set_provider(provider: DataProvider | None) -> None:
    """테스트·커스텀 백엔드 주입용."""
    global _provider
    _provider = provider


# 모듈 함수 단축 — store들이 쓰는 표면
def exists(rel: str) -> bool:
    return get_provider().exists(rel)


def read_text(rel: str) -> str:
    return get_provider().read_text(rel)


def read_json(rel: str) -> Any:
    return get_provider().read_json(rel)


def read_json_or_none(rel: str) -> Any | None:
    return get_provider().read_json_or_none(rel)


def list_paths(prefix: str) -> list[str]:
    return get_provider().list_paths(prefix)


def describe() -> dict:
    return get_provider().describe()
