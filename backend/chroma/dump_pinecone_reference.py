"""Capture the live Pinecone results as the parity baseline.

Run this with the **production** environment (the conda env the backend runs
on), so the baseline reflects the exact langchain-pinecone / pinecone-client
versions currently serving:

    conda activate sciscigpt
    python dump_pinecone_reference.py

Writes ``reference.json`` next to this file. ``test_parity.py`` then compares
the local Chroma store against it without needing Pinecone access at all.
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

import cases

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

K = 10


def serialize(doc, score=None):
	return {
		"page_content": doc.page_content,
		"metadata": doc.metadata,
	}


def main() -> int:
	from langchain_openai import OpenAIEmbeddings
	from langchain_pinecone import PineconeVectorStore

	import langchain_pinecone

	corpus_namespace = os.getenv("SCISCICORPUS_NAMESPACE")
	out = {
		"k": K,
		"provenance": {
			"corpus_index": os.getenv("SCISCICORPUS_INDEX"),
			"corpus_namespace": corpus_namespace,
			"entity_index": os.getenv("NAME_SEARCH_INDEX"),
			"langchain_pinecone": getattr(langchain_pinecone, "__version__", "unknown"),
			"python": sys.version.split()[0],
		},
		"corpus": {},
		"entities": {},
	}

	print("[corpus] querying Pinecone ...")
	corpus = PineconeVectorStore.from_existing_index(
		embedding=OpenAIEmbeddings(model="text-embedding-3-large"),
		index_name=os.getenv("SCISCICORPUS_INDEX"),
		namespace=corpus_namespace,
	)
	for label, query, kwargs in cases.CORPUS_CASES:
		flt = cases.build_filter(**kwargs)
		docs = corpus.similarity_search(query, k=K, filter=flt, namespace=corpus_namespace)
		out["corpus"][label] = {
			"query": query,
			"filter": flt,
			"results": [serialize(d) for d in docs],
		}
		print(f"  {label:<34} {len(docs)} hits")

	print("[entities] querying Pinecone ...")
	stores = {
		namespace: PineconeVectorStore.from_existing_index(
			embedding=OpenAIEmbeddings(model="text-embedding-3-small"),
			namespace=namespace,
			index_name=os.getenv("NAME_SEARCH_INDEX"),
		)
		for namespace in ("field_name", "institution_name")
	}
	for namespace, query in cases.ENTITY_CASES:
		# search_name always sends json.loads("{}")
		docs = stores[namespace].similarity_search(query, filter={}, k=K)
		out["entities"][f"{namespace}::{query}"] = {
			"namespace": namespace,
			"query": query,
			"results": [serialize(d) for d in docs],
		}
		print(f"  {namespace:<18} {query!r:<28} {len(docs)} hits")

	path = os.path.join(HERE, cases.REFERENCE_FILE)
	with open(path, "w") as handle:
		json.dump(out, handle, indent=1, ensure_ascii=False)
	size = os.path.getsize(path) / 1024 / 1024
	print(f"\nwrote {path} ({size:.1f} MB)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
