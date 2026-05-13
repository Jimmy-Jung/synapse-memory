"""ChromaDB persistent collection wrapper.

위치: ``~/.synapse/private/rag/chroma/`` (L0 격리, 0700).

ChromaDB는 자체적으로 임베딩을 만들 수도 있지만 우리는 외부에서 직접 임베드한
벡터를 ``add(embeddings=...)``로 넣음 — bge-m3 사용 명시.

Schema (각 record):
- id: unique (e.g., "card_project:dansim-ios" or "raw_obsidian:10_Active/x.md#0")
- document: redacted 텍스트 (저장 — 검색 결과 표시용)
- embedding: 1024 dim float
- metadata: {source_kind, ...}

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synapse_memory.storage.l0 import (
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

DEFAULT_COLLECTION = "synapse_memory"
DEFAULT_RAG_SUBPATH = Path("rag") / "chroma"


class VectorStoreError(RuntimeError):
    """ChromaDB 미설치 또는 연결 실패."""


@dataclass
class VectorRecord:
    """단일 벡터 저장/검색 단위."""

    id: str
    document: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """Chroma persistent collection의 얇은 래퍼.

    - lazy import (chromadb 미설치 환경에서도 모듈 import 가능)
    - sandbox-friendly: persist_dir override 가능
    """

    def __init__(self, persist_dir: Path, collection_name: str = DEFAULT_COLLECTION):
        self.persist_dir = persist_dir.expanduser().resolve()
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise VectorStoreError(
                "chromadb 미설치 — `pip install -e '.[rag]'`"
            ) from exc

        ensure_secure_dir(self.persist_dir)
        try:
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise VectorStoreError(
                f"ChromaDB 연결 실패 ({self.persist_dir}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        """동일 id 있으면 덮어쓰기. 새 record 수 + 갱신 수 합."""
        if not records:
            return 0
        self._connect()
        ids = [r.id for r in records]
        documents = [r.document for r in records]
        embeddings = [r.embedding for r in records]
        metadatas = [_clean_metadata(r.metadata) for r in records]
        try:
            self._collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise VectorStoreError(f"upsert 실패: {exc}") from exc
        return len(records)

    def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        self._connect()
        try:
            self._collection.delete(ids=list(ids))
        except Exception as exc:
            raise VectorStoreError(f"delete 실패: {exc}") from exc
        return len(ids)

    def clear(self) -> None:
        """Collection 전체 비움 (rebuild용)."""
        self._connect()
        try:
            # ChromaDB API: delete with empty where = all
            ids = self._collection.get()["ids"]
            if ids:
                self._collection.delete(ids=ids)
        except Exception as exc:
            raise VectorStoreError(f"clear 실패: {exc}") from exc

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------

    def count(self) -> int:
        self._connect()
        return int(self._collection.count())

    def query(
        self,
        embedding: list[float],
        *,
        top_k: int = 10,
        where: dict[str, object] | None = None,
    ) -> list[tuple[VectorRecord, float]]:
        """dense 벡터 검색 → ``[(record, distance), ...]`` 거리 오름차순.

        Args:
            embedding: query 벡터.
            top_k: 반환 개수.
            where: metadata filter (예: ``{"source_kind": "card_project"}``).
        """
        self._connect()
        try:
            res = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances", "embeddings"],
            )
        except Exception as exc:
            raise VectorStoreError(f"query 실패: {exc}") from exc

        results: list[tuple[VectorRecord, float]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        embs = res.get("embeddings", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, doc_id in enumerate(ids):
            rec = VectorRecord(
                id=doc_id,
                document=docs[i] if docs else "",
                embedding=list(embs[i]) if embs is not None and len(embs) > i else [],
                metadata=dict(metas[i]) if metas else {},
            )
            distance = _apply_feedback_score(float(dists[i]), rec.metadata)
            results.append((rec, distance))
        return sorted(results, key=lambda item: item[1])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """ChromaDB metadata는 scalar만 허용 (str/int/float/bool). 리스트 → 콤마.

    None은 ChromaDB가 거부 → 빈 문자열로.
    """
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple, set)):
            out[k] = ", ".join(str(x) for x in v)
        else:
            out[k] = str(v)
    return out


def _apply_feedback_score(distance: float, metadata: dict[str, Any]) -> float:
    raw_score = metadata.get("feedback_score", 1.0)
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 1.0
    if score <= 0:
        return distance
    return distance / score


def open_vector_store(
    *,
    persist_dir: Path | None = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> VectorStore:
    """기본 위치 (``~/.synapse/private/rag/chroma``)의 store 열기."""
    if persist_dir is None:
        ensure_l0_root_secure()
        persist_dir = l0_root() / DEFAULT_RAG_SUBPATH
    return VectorStore(persist_dir=persist_dir, collection_name=collection_name)
