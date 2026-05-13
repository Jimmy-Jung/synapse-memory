"""embeddings.py 테스트 — sentence-transformers 미설치 환경에서도 통과하도록 mock.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapse_memory.rag import embeddings as emb_mod
from synapse_memory.rag.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingError,
    EmbeddingUnavailableError,
    embed_query,
    embed_texts,
    get_embedder,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """매 테스트마다 모듈 전역 캐시 리셋."""
    emb_mod._EMBEDDER = None
    emb_mod._LOADED_MODEL = None
    yield
    emb_mod._EMBEDDER = None
    emb_mod._LOADED_MODEL = None


class TestGetEmbedder:
    def test_missing_sdk_raises(self) -> None:
        """sentence-transformers import 실패 → EmbeddingUnavailableError."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sentence_transformers" or name.startswith("sentence_transformers."):
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            pytest.raises(EmbeddingUnavailableError, match="미설치"),
        ):
            get_embedder()

    def test_caches_instance(self) -> None:
        """같은 모델 두 번 요청 → 같은 instance."""
        fake = MagicMock(name="SentenceTransformer")
        with patch.dict(
            "sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=lambda *a, **kw: fake)}
        ):
            e1 = get_embedder("model-X")
            e2 = get_embedder("model-X")
            assert e1 is e2


class TestEmbedTexts:
    def _setup_fake(self, vectors: list[list[float]]) -> MagicMock:
        fake = MagicMock(name="SentenceTransformer")
        # numpy array 흉내 — .tolist() 가능
        import numpy as np
        fake.encode.return_value = np.array(vectors, dtype="float32")
        return fake

    def test_returns_vectors(self) -> None:
        fake = self._setup_fake([[0.1, 0.2], [0.3, 0.4]])
        with patch("synapse_memory.rag.embeddings.get_embedder", return_value=fake):
            result = embed_texts(["a", "b"])
        assert len(result) == 2
        assert len(result[0]) == 2
        assert pytest.approx(result[0][0]) == 0.1

    def test_empty_input(self) -> None:
        assert embed_texts([]) == []

    def test_passes_kwargs(self) -> None:
        fake = self._setup_fake([[0.1]])
        with patch("synapse_memory.rag.embeddings.get_embedder", return_value=fake):
            embed_texts(["x"], batch_size=8, normalize=False)
        kw = fake.encode.call_args.kwargs
        assert kw["batch_size"] == 8
        assert kw["normalize_embeddings"] is False

    def test_encode_failure_wrapped(self) -> None:
        fake = MagicMock()
        fake.encode.side_effect = RuntimeError("OOM")
        with (
            patch("synapse_memory.rag.embeddings.get_embedder", return_value=fake),
            pytest.raises(EmbeddingError, match="OOM"),
        ):
            embed_texts(["x"])


class TestEmbedQuery:
    def test_single(self) -> None:
        import numpy as np
        fake = MagicMock()
        fake.encode.return_value = np.array([[0.5, 0.6]], dtype="float32")
        with patch("synapse_memory.rag.embeddings.get_embedder", return_value=fake):
            v = embed_query("질의")
        assert v == pytest.approx([0.5, 0.6])

    def test_empty_raises(self) -> None:
        with pytest.raises(EmbeddingError):
            embed_query("")


def test_default_model_is_bge_m3() -> None:
    assert DEFAULT_EMBEDDING_MODEL == "BAAI/bge-m3"
