"""Pinecone-compatible Chroma vector store for SciSciGPT.

The tools only ever call one method::

    similarity_search(query, filter=..., k=..., namespace=...)

and consume ``Document.page_content`` / ``Document.metadata``. This adapter
reproduces that contract on top of a local Chroma collection so that
``literature.py`` and ``name.py`` keep working unchanged.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore


# ── filter translation ────────────────────────────────────────────────────
# Pinecone and Chroma use nearly the same filter dialect, but three
# differences bite in practice, and every one of them is reachable from the
# current call sites:
#
#   1. Chroma rejects ``$and`` / ``$or`` with fewer than two operands.
#      ``__search_and_format__`` builds ``{"$and": [<one condition>]}``
#      whenever exactly one search constraint is set.
#   2. Chroma rejects an empty ``where``. ``search_name`` passes
#      ``json.loads("{}")`` on every single call.
#   3. numpy scalars coming out of pandas are not valid Chroma operands.

_LOGICAL = ("$and", "$or")


def _scalar(value: Any) -> Any:
	"""Coerce numpy/pandas scalars to plain Python for Chroma."""
	item = getattr(value, "item", None)
	if callable(item) and not isinstance(value, (str, bytes)):
		try:
			return item()
		except (ValueError, TypeError):
			pass
	return value


def _leaf(value: Any) -> dict:
	if isinstance(value, dict):
		return {op: _scalar(v) for op, v in value.items()}
	if isinstance(value, (list, tuple, set)):
		return {"$in": [_scalar(v) for v in value]}
	return {"$eq": _scalar(value)}


def translate_filter(node: Any) -> Optional[dict]:
	"""Pinecone-style filter -> Chroma ``where``. ``None`` means "no filter"."""
	if node is None:
		return None
	if not isinstance(node, dict):
		raise TypeError(f"filter must be a dict, got {type(node).__name__}")
	if not node:
		return None  # `{}` would raise inside Chroma

	clauses: list[dict] = []
	for key, value in node.items():
		if key in _LOGICAL:
			if not isinstance(value, (list, tuple)):
				raise TypeError(f"{key} expects a list, got {type(value).__name__}")
			subs = [s for s in (translate_filter(v) for v in value) if s is not None]
			if not subs:
				continue
			# Chroma requires >= 2 operands; a single one is just the operand.
			clauses.append(subs[0] if len(subs) == 1 else {key: subs})
		else:
			clauses.append({key: _leaf(value)})

	if not clauses:
		return None
	return clauses[0] if len(clauses) == 1 else {"$and": clauses}


# ── vector store ──────────────────────────────────────────────────────────

class ChromaVectorStore(VectorStore):
	"""Read-only Chroma-backed store matching the Pinecone call contract.

	``namespace`` is mapped to a Chroma collection. Because the corpus lives in
	a single collection, an unexpected namespace raises rather than silently
	searching the wrong data.
	"""

	def __init__(
		self,
		*,
		collection,
		embedding,
		namespace_aliases: Sequence[str] = (),
	) -> None:
		self._collection = collection
		self._embedding = embedding
		# The namespace the caller is allowed to ask for, plus None.
		self._aliases = {a for a in namespace_aliases if a} | {collection.name}

	@property
	def embeddings(self):
		return self._embedding

	def _resolve(self, namespace: Optional[str]):
		if namespace is None or namespace in self._aliases:
			return self._collection
		raise ValueError(
			f"namespace {namespace!r} is not served by collection "
			f"{self._collection.name!r} (known: {sorted(self._aliases)})"
		)

	def similarity_search(
		self,
		query: str,
		k: int = 10,
		filter: Optional[dict] = None,
		namespace: Optional[str] = None,
		**kwargs: Any,
	) -> list[Document]:
		docs_and_scores = self.similarity_search_with_score(
			query, k=k, filter=filter, namespace=namespace, **kwargs
		)
		return [doc for doc, _ in docs_and_scores]

	def similarity_search_with_score(
		self,
		query: str,
		k: int = 10,
		filter: Optional[dict] = None,
		namespace: Optional[str] = None,
		**kwargs: Any,
	) -> list[tuple[Document, float]]:
		collection = self._resolve(namespace)
		where = translate_filter(filter)
		vector = self._embedding.embed_query(query)

		result = collection.query(
			query_embeddings=[vector],
			n_results=max(int(k), 1),
			where=where,
			include=["documents", "metadatas", "distances"],
		)

		ids = result.get("ids") or [[]]
		documents = (result.get("documents") or [[]])[0] or []
		metadatas = (result.get("metadatas") or [[]])[0] or []
		distances = (result.get("distances") or [[]])[0] or []

		out: list[tuple[Document, float]] = []
		for i, doc_id in enumerate(ids[0]):
			# Pinecone hands metadata back with keys in alphabetical order;
			# Chroma's order comes out of SQLite and is arbitrary. That is not
			# cosmetic: `pd.DataFrame([...]).to_markdown()` in search_name and
			# `__dict_to_bibtex__` in search_literature both render fields in
			# dict order, so an unsorted dict changes what the model reads.
			raw = metadatas[i] if i < len(metadatas) else None
			metadata = {key: raw[key] for key in sorted(raw)} if raw else {}
			content = documents[i] if i < len(documents) else ""
			# cosine space: distance = 1 - cosine similarity
			score = 1.0 - distances[i] if i < len(distances) else 0.0
			out.append((Document(id=doc_id, page_content=content or "", metadata=metadata), score))
		return out

	# ── write path: this store is built offline by build_index.py ──────────

	def add_texts(self, texts: Iterable[str], metadatas: Optional[list[dict]] = None, **kwargs: Any):
		raise NotImplementedError(
			"ChromaVectorStore is read-only; build the index with build_index.py"
		)

	@classmethod
	def from_texts(cls, texts, embedding, metadatas=None, **kwargs):
		raise NotImplementedError(
			"ChromaVectorStore is read-only; build the index with build_index.py"
		)
