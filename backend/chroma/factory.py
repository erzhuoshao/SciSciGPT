"""Ready-to-use store constructors, so integration is a two-line change.

Nothing in ``backend/tools`` imports this yet. When you are ready, the swap in
``literature.py`` and ``name.py`` becomes::

    from chroma.factory import make_corpus_store, make_entity_stores

    vs = make_corpus_store(openai_api_key=openai_api_key)          # literature.py
    vectorstore_dict = make_entity_stores()                        # name.py

Both return objects that satisfy the same contract ``PineconeVectorStore`` did:
subclasses of ``langchain_core.vectorstores.VectorStore`` exposing
``similarity_search(query, k=..., filter=..., namespace=...)`` and returning
``Document`` objects with the same ``page_content`` / ``metadata`` layout.

Verify the store is present and healthy before wiring anything up::

    python -c "from chroma.factory import health; print(health())"
"""

from __future__ import annotations

import os
from typing import Optional

try:
	# imported as a package from the backend (tools/literature.py, tools/name.py)
	from . import config
	from .chroma_vs import ChromaVectorStore
except ImportError:
	# run as a script from inside backend/chroma (python factory.py)
	import config
	from chroma_vs import ChromaVectorStore

_client = None


def get_client():
	"""One PersistentClient per process; Chroma handles concurrent reads."""
	global _client
	if _client is None:
		import chromadb

		if not os.path.isdir(config.CHROMA_PATH):
			raise FileNotFoundError(
				f"no Chroma store at {config.CHROMA_PATH}. "
				"Build it first: python build_index.py --reset"
			)
		_client = chromadb.PersistentClient(path=config.CHROMA_PATH)
	return _client


def make_corpus_store(openai_api_key: Optional[str] = None) -> ChromaVectorStore:
	"""Replacement for the ``vs`` built at literature.py:288."""
	from langchain_openai import OpenAIEmbeddings

	namespace = os.getenv("SCISCICORPUS_NAMESPACE")
	return ChromaVectorStore(
		collection=get_client().get_collection(config.CORPUS_COLLECTION),
		embedding=OpenAIEmbeddings(
			model=config.CORPUS_EMBEDDING_MODEL,
			api_key=openai_api_key or os.getenv("OPENAI_API_KEY"),
		),
		# literature.py passes the Pinecone namespace on every call; accept it.
		namespace_aliases=(namespace,) if namespace else (),
	)


def make_entity_stores() -> dict[str, ChromaVectorStore]:
	"""Replacement for the ``vectorstore_dict`` built at name.py:64-70."""
	from langchain_openai import OpenAIEmbeddings

	client = get_client()
	embedding = OpenAIEmbeddings(model=config.ENTITY_EMBEDDING_MODEL)
	return {
		namespace: ChromaVectorStore(
			collection=client.get_collection(namespace),
			embedding=embedding,
			namespace_aliases=(namespace,),
		)
		for namespace in (config.FIELD_COLLECTION, config.INSTITUTION_COLLECTION)
	}


def health() -> dict:
	"""Collection counts vs expectations. Safe to call at startup."""
	client = get_client()
	report = {"path": config.CHROMA_PATH, "collections": {}, "ok": True}
	for name, expected in config.EXPECTED_COUNTS.items():
		try:
			actual = client.get_collection(name).count()
		except Exception as exc:
			report["collections"][name] = f"MISSING ({type(exc).__name__})"
			report["ok"] = False
			continue
		report["collections"][name] = {"count": actual, "expected": expected}
		if actual != expected:
			report["ok"] = False
	return report


if __name__ == "__main__":
	import json

	print(json.dumps(health(), indent=2))
