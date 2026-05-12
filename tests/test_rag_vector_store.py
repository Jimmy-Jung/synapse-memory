"""vector_store.py 테스트 — chromadb 미설치 환경에서도 mock으로.

저자: JunyoungJung <joony300</tt>"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse_memory.rag.vector_store import (
    DEFAULT_COLLECTION,
    VectorRecord,
    VectorStore,
    VectorStoreError,
    _clean_metadata,
)


class TestCleanMetadata:
    def test_scalars_passed(self) -> None:
        out = _clean_metadata({"a": "x", "b": 1, "c": 1.5, "d": True})
        assert out == {"a": "x", "b": 1, "c": 1.5, "d": True}

    def test_none_to_empty_string(self) -> None:
        assert _clean_metadata({"a": None})["a"] == ""

    def test_list_joined_with_comma(self) -> None:
        assert _clean_metadata({"tags": ["x", "y", "z"]})["tags"] == "x, y, z"

    def test_other_stringified(self) -> None:
        assert _clean_metadata({"p": Path("/x")})["p"] == "/x"


class TestVectorStore:
    def _fake_chroma(self, collection_mock: MagicMock):
        mod = MagicMock()
        client = MagicMock()
        client.get_or_create_collection.return_value = collection_mock
        mod.PersistentClient.return_value = client
        return mod

    def test_missing_chromadb_raises(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "chroma")
        # chromadb import 실패 시뮬레이션
        import builtins
        real = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "chromadb":
                raise ImportError("nope")
            return real(name, *a, **kw)

        with patch("builtins.__import__", side_effect=fake_import), pytest.raises(
            VectorStoreError, match="미설치"
        ):
            store.upsert([VectorRecord("x", "doc", [0.1])])

    def test_upsert_calls_collection(self, tmp_path: Path) -> None:
        coll = MagicMock()
        coll.count.return_value = 0
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            n = store.upsert([
                VectorRecord("a", "doc-a", [0.1, 0.2], {"kind": "card"}),
                VectorRecord("b", "doc-b", [0.3, 0.4], {"kind": "raw", "tags": ["x", "y"]}),
            ])
        assert n == 2
        kw = coll.upsert.call_args.kwargs
        assert kw["ids"] == ["a", "b"]
        assert kw["documents"] == ["doc-a", "doc-b"]
        # tags가 콤마로 join됨
        assert kw["metadatas"][1]["tags"] == "x, y"

    def test_upsert_empty_no_call(self, tmp_path: Path) -> None:
        coll = MagicMock()
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            n = store.upsert([])
        assert n == 0
        coll.upsert.assert_not_called()

    def test_query_returns_records(self, tmp_path: Path) -> None:
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [["a", "b"]],
            "documents": [["doc-a", "doc-b"]],
            "metadatas": [[{"kind": "card"}, {"kind": "raw"}]],
            "embeddings": [[[0.1, 0.2], [0.3, 0.4]]],
            "distances": [[0.0, 0.5]],
        }
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            results = store.query([0.1, 0.2], top_k=2)

        assert len(results) == 2
        rec0, dist0 = results[0]
        assert rec0.id == "a"
        assert rec0.document == "doc-a"
        assert rec0.metadata["kind"] == "card"
        assert dist0 == 0.0

    def test_query_applies_feedback_score(self, tmp_path: Path) -> None:
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [["low", "high"]],
            "documents": [["low doc", "high doc"]],
            "metadatas": [[
                {"feedback_score": 0.5},
                {"feedback_score": 1.5},
            ]],
            "embeddings": [[[0.1], [0.2]]],
            "distances": [[0.2, 0.2]],
        }
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            results = store.query([0.1], top_k=2)

        assert [record.id for record, _ in results] == ["high", "low"]
        assert results[0][1] < results[1][1]

    def test_count(self, tmp_path: Path) -> None:
        coll = MagicMock()
        coll.count.return_value = 42
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            assert store.count() == 42

    def test_delete(self, tmp_path: Path) -> None:
        coll = MagicMock()
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            n = store.delete(["a", "b"])
        assert n == 2
        coll.delete.assert_called_once()

    def test_clear_deletes_all(self, tmp_path: Path) -> None:
        coll = MagicMock()
        coll.get.return_value = {"ids": ["a", "b", "c"]}
        with patch.dict("sys.modules", {"chromadb": self._fake_chroma(coll)}):
            store = VectorStore(persist_dir=tmp_path / "c")
            store.clear()
        coll.delete.assert_called_with(ids=["a", "b", "c"])


def test_default_collection_name() -> None:
    assert DEFAULT_COLLECTION == "synapse_memory"
