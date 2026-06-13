# -*- coding: utf-8 -*-
"""SQLite 스냅샷 관리 — 빌드(pack)·검증(validate)·자동 다운로드(ensure).

스냅샷 포맷 (alio_snapshot.db):
- meta(key, value): format_version·built_at·doc_count 등
- docs(path, content): data/ 상대경로 → zlib 압축된 JSON/텍스트

배포 흐름:
  scripts/build_snapshot.py → GitHub Release 자산(alio_snapshot.db)
  → 최초 실행 시 ensure_snapshot()이 사용자 데이터 디렉터리로 다운로드.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("open-alio-mcp.snapshot")

SNAPSHOT_FORMAT_VERSION = "1"
SNAPSHOT_FILENAME = "alio_snapshot.db"
DEFAULT_SNAPSHOT_URL = (
    "https://github.com/gitbosung/open-ALIO-mcp/releases/latest/download/alio_snapshot.db"
)

# 스냅샷이 반드시 담아야 하는 핵심 문서 — 검증 기준
REQUIRED_DOCS = (
    "aliases.json",
    "institutions.json",
    "metrics/_index.json",
    "reference/disclosure_items.json",
    "reference/related_laws.json",
)

# data/ 디렉터리에서 스냅샷에 담을 런타임 파일 (glob, data/ 기준 상대경로)
RUNTIME_DATA_GLOBS = (
    "aliases.json",
    "institutions.json",
    "metrics/*.json",
    "parsed/by-org/*.json",
    "reference/*.json",
    "guidelines/*.json",
    "handbook/*.json",
    "snapshots/recruitments_ongoing.json",
)

# 런타임에 쓰지 않는 빌드 리포트·검증 시드는 제외
EXCLUDE_NAMES = (
    "_crawl_promotion_report.json",
    "golden_samples.json",
    "live_validation_seeds.json",
)


class SnapshotError(Exception):
    pass


def default_snapshot_dir() -> Path:
    """플랫폼별 사용자 데이터 디렉터리 (예: %LOCALAPPDATA%/open-alio-mcp)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "open-alio-mcp"


def default_snapshot_path() -> Path:
    return default_snapshot_dir() / SNAPSHOT_FILENAME


# ── 빌드 (scripts/build_snapshot.py에서 사용) ─────────────────────────────────


def iter_runtime_files(data_dir: Path):
    """data/ 안에서 스냅샷 대상 파일을 (상대경로, 절대경로)로 순회."""
    seen: set[str] = set()
    for pattern in RUNTIME_DATA_GLOBS:
        for path in sorted(data_dir.glob(pattern)):
            if not path.is_file() or path.name in EXCLUDE_NAMES:
                continue
            rel = path.relative_to(data_dir).as_posix()
            if rel not in seen:
                seen.add(rel)
                yield rel, path


def pack_data_dir(data_dir: Path, dest: Path) -> dict:
    """data/ 런타임 파일을 SQLite 스냅샷 1개로 패킹. 메타 정보를 반환."""
    data_dir = Path(data_dir)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    conn = sqlite3.connect(dest)
    try:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE docs (path TEXT PRIMARY KEY, content BLOB NOT NULL)")
        count = 0
        raw_bytes = 0
        for rel, path in iter_runtime_files(data_dir):
            raw = path.read_bytes()
            raw_bytes += len(raw)
            conn.execute(
                "INSERT INTO docs (path, content) VALUES (?, ?)",
                (rel, zlib.compress(raw, 9)),
            )
            count += 1
        missing = [d for d in REQUIRED_DOCS if not _doc_exists(conn, d)]
        if missing:
            raise SnapshotError(f"필수 문서 누락으로 스냅샷 빌드 실패: {missing}")
        meta = {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "doc_count": str(count),
            "raw_bytes": str(raw_bytes),
        }
        conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta.items())
        conn.commit()
    finally:
        conn.close()
    return {**meta, "doc_count": count, "raw_bytes": raw_bytes, "path": str(dest)}


def _doc_exists(conn: sqlite3.Connection, rel: str) -> bool:
    return conn.execute("SELECT 1 FROM docs WHERE path = ?", (rel,)).fetchone() is not None


# ── 검증 ──────────────────────────────────────────────────────────────────────


def read_meta(path: Path) -> dict:
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        return dict(conn.execute("SELECT key, value FROM meta"))
    finally:
        conn.close()


def validate_snapshot(path: Path) -> tuple[bool, str]:
    """스냅샷 파일이 열리고 포맷·필수 문서를 갖췄는지 확인. (ok, 사유)."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return False, "파일 없음 또는 0바이트"
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            if meta.get("format_version") != SNAPSHOT_FORMAT_VERSION:
                return False, f"format_version 불일치: {meta.get('format_version')}"
            missing = [d for d in REQUIRED_DOCS if not _doc_exists(conn, d)]
            if missing:
                return False, f"필수 문서 누락: {missing}"
            # 샘플 1건 압축 해제로 손상 여부 확인
            row = conn.execute(
                "SELECT content FROM docs WHERE path = ?", (REQUIRED_DOCS[0],)
            ).fetchone()
            zlib.decompress(row[0])
        finally:
            conn.close()
    except (sqlite3.Error, zlib.error, OSError) as e:
        return False, f"손상된 스냅샷: {e}"
    return True, "ok"


# ── 다운로드 (ensure_snapshot) ────────────────────────────────────────────────


def _download(url: str, dest: Path, timeout: int = 120) -> None:
    """url → dest 원자적 다운로드. 가능하면 .sha256 사이드카로 무결성 검증."""
    import requests  # 지연 임포트 — 오프라인 검증·빌드 경로에서는 불필요

    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("스냅샷 다운로드 시작: %s", url)
    resp = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()

    digest = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                digest.update(chunk)

        expected = _fetch_sha256_sidecar(url, timeout)
        if expected and expected != digest.hexdigest():
            raise SnapshotError(
                f"스냅샷 sha256 불일치 — expected {expected[:12]}…, got {digest.hexdigest()[:12]}…"
            )
        ok, reason = validate_snapshot(tmp)
        if not ok:
            raise SnapshotError(f"다운로드한 스냅샷 검증 실패: {reason}")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("스냅샷 저장 완료: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)


def _fetch_sha256_sidecar(url: str, timeout: int) -> str | None:
    """<asset>.sha256 사이드카가 있으면 해시 문자열 반환 (없으면 None — best effort)."""
    import requests

    try:
        r = requests.get(url + ".sha256", timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and r.text.strip():
            return r.text.split()[0].strip().lower()
    except requests.RequestException:
        pass
    return None


def ensure_snapshot(path: Path | None = None, url: str | None = None, force: bool = False) -> Path:
    """로컬 스냅샷 존재·무결성 확인 후 경로 반환. 없거나 손상이면 다운로드.

    환경변수: OPEN_ALIO_SNAPSHOT_URL로 다운로드 출처를 바꿀 수 있다.
    """
    path = Path(path) if path else default_snapshot_path()
    url = url or os.environ.get("OPEN_ALIO_SNAPSHOT_URL") or DEFAULT_SNAPSHOT_URL

    if not force and path.exists():
        ok, reason = validate_snapshot(path)
        if ok:
            return path
        log.warning("기존 스냅샷 무효(%s) — 재다운로드합니다: %s", reason, path)

    try:
        _download(url, path)
    except SnapshotError:
        raise
    except Exception as e:  # 네트워크·권한 등 — 사용자 안내 메시지로 변환
        raise SnapshotError(
            f"스냅샷 다운로드 실패: {e}\n"
            f"  URL: {url}\n"
            "  네트워크 연결을 확인하거나, 수동으로 받은 파일을 "
            f"{path} 에 두거나, OPEN_ALIO_DATA_DIR로 data/ 디렉터리를 지정하세요."
        ) from e
    return path
