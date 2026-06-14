import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from pylate.indexes import PLAID
from pylate.models import ColBERT as ColBERTModel
from pylate.retrieve import ColBERT as ColBERTRetriever

from gfmrag.graph_index_construction.utils import processing_phrases

from .base_model import BaseELModel

logger = logging.getLogger(__name__)

ENCODE_BATCH_SIZE = 32
QUERY_BATCH_SIZE = 32


class ColbertELModel(BaseELModel):
    def __init__(
        self,
        model_name_or_path: str = "lightonai/GTE-ModernColBERT-v1",
        root: str = "tmp",
        force: bool = False,
        batch_size: int = ENCODE_BATCH_SIZE,
        use_fast: bool = False,
        cache_dir: str | None = None,
        **_: Any,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.root = root
        self.force = force
        self.batch_size = batch_size
        self.use_fast = use_fast
        # Optional durable cache for the PLAID index. The build is deterministic
        # given (entity_list, model), so on an ephemeral `root` (e.g. a Cloud Run
        # /tmp) we seed it from `cache_dir` to skip the ~14-18min rebuild, and copy
        # a freshly-built index back. Build/load stay on local `root` (mmap-safe);
        # `cache_dir` is a plain directory (e.g. a writable gcsfuse mount) touched
        # only by file copies. No-op when unset; no extra dependencies.
        self.cache_dir = cache_dir
        self.model = ColBERTModel(model_name_or_path=model_name_or_path)
        self._retriever: ColBERTRetriever | None = None

    def _cache_index_root(self, fingerprint: str) -> Path:
        model_slug = self.model_name_or_path.replace("/", "_")
        return Path(self.cache_dir) / "pylate" / model_slug / fingerprint  # type: ignore[arg-type]

    def _index_root(self, fingerprint: str) -> Path:
        model_slug = self.model_name_or_path.replace("/", "_")
        return Path(self.root) / "pylate" / model_slug / fingerprint

    def _metadata_path(self, fingerprint: str) -> Path:
        return self._index_root(fingerprint) / "metadata.json"

    def _load_metadata(self, fingerprint: str) -> dict[str, Any] | None:
        path = self._metadata_path(fingerprint)
        if not path.exists():
            return None
        with path.open() as f:
            return json.load(f)

    def _write_metadata(self, fingerprint: str, entity_list: list[str]) -> None:
        path = self._metadata_path(fingerprint)
        with path.open("w") as f:
            json.dump(
                {
                    "fingerprint": fingerprint,
                    "model_name_or_path": self.model_name_or_path,
                    "entity_list": entity_list,
                },
                f,
            )

    def index(self, entity_list: list) -> None:
        self.entity_list = entity_list
        fingerprint = hashlib.md5("".join(entity_list).encode()).hexdigest()
        index_root = self._index_root(fingerprint)
        expected_metadata = {
            "fingerprint": fingerprint,
            "model_name_or_path": self.model_name_or_path,
            "entity_list": entity_list,
        }

        # Seed an ephemeral root from the durable cache before deciding to
        # rebuild. Best-effort: any failure falls through to a local build.
        if self.cache_dir and not self.force and not index_root.exists():
            cached = self._cache_index_root(fingerprint)
            if cached.exists():
                try:
                    shutil.copytree(cached, index_root)
                    logger.info("ColBERT index seeded from cache %s", cached)
                except Exception as e:  # noqa: BLE001
                    logger.warning("ColBERT cache seed failed (%s); rebuilding", e)

        existing_metadata = self._load_metadata(fingerprint)
        should_reuse = (
            not self.force
            and index_root.exists()
            and existing_metadata == expected_metadata
        )

        if not should_reuse:
            if self.force and index_root.exists():
                shutil.rmtree(index_root)
            index_root.mkdir(parents=True, exist_ok=True)

            phrases = [processing_phrases(p) for p in entity_list]
            doc_embeddings = self.model.encode(
                phrases,
                batch_size=self.batch_size,
                is_query=False,
                show_progress_bar=True,
            )

            plaid = PLAID(
                index_folder=str(index_root),
                index_name="plaid",
                override=True,
                use_fast=self.use_fast,
            )
            plaid.add_documents(
                documents_ids=[str(i) for i in range(len(entity_list))],
                documents_embeddings=doc_embeddings,
            )
            self._write_metadata(fingerprint, entity_list)
            # Persist the freshly-built index so the next cold start reuses it.
            if self.cache_dir:
                cached = self._cache_index_root(fingerprint)
                try:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(index_root, cached, dirs_exist_ok=True)
                    logger.info("ColBERT index persisted to cache %s", cached)
                except Exception as e:  # noqa: BLE001
                    logger.warning("ColBERT cache persist failed (%s)", e)
        else:
            self.entity_list = existing_metadata["entity_list"]  # type: ignore[index]
            plaid = PLAID(
                index_folder=str(index_root),
                index_name="plaid",
                override=False,
                use_fast=self.use_fast,
            )

        self._retriever = ColBERTRetriever(index=plaid)

    def __call__(self, ner_entity_list: list, topk: int = 1) -> dict:
        if self._retriever is None or not hasattr(self, "entity_list"):
            raise AttributeError("Index the entities first using index method")

        queries = [processing_phrases(p) for p in ner_entity_list]
        query_embeddings = self.model.encode(
            queries,
            batch_size=self.batch_size,
            is_query=True,
            show_progress_bar=False,
        )

        scores = self._retriever.retrieve(queries_embeddings=query_embeddings, k=topk)

        linked_entity_dict: dict[str, list] = {}
        for query, hits in zip(ner_entity_list, scores, strict=False):
            max_score = hits[0]["score"] if hits else 1.0
            linked_entity_dict[query] = [
                {
                    "entity": self.entity_list[int(hit["id"])],
                    "score": hit["score"],
                    "norm_score": hit["score"] / max_score if max_score else 0.0,
                }
                for hit in hits
            ]

        return linked_entity_dict
