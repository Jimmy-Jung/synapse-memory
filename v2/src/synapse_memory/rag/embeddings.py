"""bge-m3 로컬 임베딩 wrapper.

- 모델: ``BAAI/bge-m3`` (한국어/영어/100+ 언어, 8K 컨텍스트, dense+sparse+multi-vector)
- 백엔드: sentence-transformers (Apple Silicon은 MPS 자동)
- 캐싱: 모델은 lazy 로드, 한 번 로드 후 모듈 전역 보관

**v2 보안**: 입력은 redacted 텍스트만. raw 임베드 금지 (caller 책임).

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024  # bge-m3 dense dimension


class EmbeddingError(RuntimeError):
    """임베딩 실패."""


class EmbeddingUnavailableError(EmbeddingError):
    """sentence-transformers 미설치 또는 모델 로드 실패."""


# 모듈 전역 cache — 모델 로드 비싸므로 한 번만
_EMBEDDER: Any = None
_LOADED_MODEL: str | None = None


def get_embedder(model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
    """SentenceTransformer 인스턴스 lazy 로드 + cache.

    같은 모델 이름이면 cached 인스턴스 반환. 다른 모델 요청하면 재로드.

    Raises:
        EmbeddingUnavailableError: sentence-transformers 미설치.
    """
    global _EMBEDDER, _LOADED_MODEL

    if _EMBEDDER is not None and _LOADED_MODEL == model_name:
        return _EMBEDDER

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EmbeddingUnavailableError(
            "sentence-transformers 미설치 — `pip install -e '.[rag]'`"
        ) from exc

    try:
        _EMBEDDER = SentenceTransformer(model_name, trust_remote_code=False)
        _LOADED_MODEL = model_name
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingUnavailableError(
            f"임베딩 모델 로드 실패 ({model_name}): {exc}"
        ) from exc
    return _EMBEDDER


def embed_texts(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
    normalize: bool = True,
    show_progress_bar: bool = False,
) -> list[list[float]]:
    """텍스트 리스트 → 임베딩 벡터 리스트.

    Args:
        texts: 인코딩 대상 (redacted 권장).
        model_name: HF model id.
        batch_size: GPU/CPU에 맞춰 조정.
        normalize: cosine 유사도 사용 시 True (dense 정규화).
        show_progress_bar: 대량 인덱싱 시 True.

    Returns:
        ``[len(texts) × EMBEDDING_DIM]`` float 리스트.
    """
    if not texts:
        return []

    embedder = get_embedder(model_name)
    try:
        vectors = embedder.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress_bar,
            convert_to_numpy=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"인코딩 실패: {exc}") from exc

    return [v.tolist() for v in vectors]


def embed_query(
    query: str,
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    normalize: bool = True,
) -> list[float]:
    """단일 쿼리 임베딩 — search 시 사용."""
    if not query:
        raise EmbeddingError("빈 query는 임베드 못 함")
    result = embed_texts(
        [query], model_name=model_name, normalize=normalize, batch_size=1
    )
    return result[0]
