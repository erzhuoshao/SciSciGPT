"""Compare the local Chroma store against the captured Pinecone baseline.

The baseline is produced by ``dump_pinecone_reference.py`` running in the
production conda env, so this test needs no Pinecone access and pins the
comparison to the versions actually serving today.

    ./.venv/bin/python test_parity.py

Checks, in order:

  1. filter translation -- the Pinecone -> Chroma dialect differences
  2. corpus retrieval    -- same documents, same order, per filter shape
  3. corpus payload      -- page_content and metadata byte-identical
  4. entity retrieval    -- same rows, and the same rendered markdown that
                            ``search_name`` hands back to the LLM
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv

import cases
import config
from chroma_vs import ChromaVectorStore, translate_filter

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
	results.append((PASS if ok else FAIL, name, detail))
	print(f"  [{PASS if ok else FAIL}] {name}" + (f"  --  {detail}" if detail else ""))


def load_reference() -> dict:
	path = os.path.join(HERE, cases.REFERENCE_FILE)
	if not os.path.exists(path):
		sys.exit(
			f"missing {path}\n"
			"run `conda activate sciscigpt && python dump_pinecone_reference.py` first"
		)
	with open(path) as handle:
		return json.load(handle)


def store(collection_name: str, model: str, aliases=()) -> ChromaVectorStore:
	import chromadb
	from langchain_openai import OpenAIEmbeddings

	client = chromadb.PersistentClient(path=config.CHROMA_PATH)
	return ChromaVectorStore(
		collection=client.get_collection(collection_name),
		embedding=OpenAIEmbeddings(model=model),
		namespace_aliases=aliases,
	)


# ── normalisation ─────────────────────────────────────────────────────────
# Pinecone coerces every metadata number to float; Chroma preserves int.
# Compare on a view where all numbers are floats.

def norm_value(value):
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return float(value)
	return value


def norm_meta(metadata: dict) -> dict:
	return {k: norm_value(v) for k, v in metadata.items()}


def doc_key(metadata: dict) -> str:
	url = metadata.get("url")
	section_id = metadata.get("section_id")
	if isinstance(section_id, float) and section_id.is_integer():
		section_id = int(section_id)
	return f"{url}::{section_id}"


# ── checks ────────────────────────────────────────────────────────────────

def check_filter_translation() -> None:
	print("\n=== 1. filter translation ===")
	checks = [
		("empty dict -> None (name.py sends this every call)", {}, None),
		("None -> None", None, None),
		("single $and unwrapped (literature.py:142)",
		 {"$and": [{"year": {"$gte": 2015}}]}, {"year": {"$gte": 2015}}),
		("two $and preserved",
		 {"$and": [{"year": {"$gte": 2010}}, {"year": {"$lte": 2020}}]},
		 {"$and": [{"year": {"$gte": 2010}}, {"year": {"$lte": 2020}}]}),
		("bare value -> $eq", {"section_category": "Results"},
		 {"section_category": {"$eq": "Results"}}),
		("nested $or preserved",
		 {"$and": [{"$or": [{"journaltitle": "Nature"}, {"publisher": "Nature"}]}]},
		 {"$or": [{"journaltitle": {"$eq": "Nature"}}, {"publisher": {"$eq": "Nature"}}]}),
		("$and of empties -> None", {"$and": []}, None),
	]
	for label, given, expected in checks:
		record(f"translate / {label}", translate_filter(given) == expected,
		       f"got={translate_filter(given)}")


# Pinecone is itself an approximate index, so it is not ground truth. When the
# two backends disagree, brute-force exact search over our own vectors decides
# which one is right -- and in practice it has been Pinecone that drifts, on
# near-ties (one observed gap: 0.416245 vs 0.416207).
# Rows we are willing to pull into memory to arbitrate. 10k covers both entity
# collections (6,969 x 1536 float64 = 86 MB) and any realistically filtered
# corpus subset; the unfiltered 24,858-row corpus is deliberately out of scope.
ARBITRATION_LIMIT = 10000


def exact_topk(collection, where, vector, k, key_fn):
	"""Brute-force top-k over the subset matching `where`. None if too large."""
	import numpy as np

	subset = collection.get(where=where, include=["embeddings", "metadatas"])
	metadatas = subset["metadatas"] or []
	if not metadatas or len(metadatas) > ARBITRATION_LIMIT:
		return None
	matrix = np.asarray(subset["embeddings"], dtype="float64")
	matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
	query = np.asarray(vector, dtype="float64")
	query = query / np.linalg.norm(query)
	order = np.argsort(-(matrix @ query))[:k]
	return [key_fn(metadatas[i]) for i in order]


def check_corpus(reference: dict) -> None:
	print("\n=== 2. corpus retrieval ===")
	namespace = reference["provenance"]["corpus_namespace"]
	chroma = store(config.CORPUS_COLLECTION, config.CORPUS_EMBEDDING_MODEL, aliases=(namespace,))
	collection = chroma._collection
	k = reference["k"]

	for label, query, kwargs in cases.CORPUS_CASES:
		expected = reference["corpus"].get(label)
		if expected is None:
			record(f"corpus / {label}", False, "missing from reference")
			continue
		flt = cases.build_filter(**kwargs)
		try:
			docs = chroma.similarity_search(query, k=k, filter=flt, namespace=namespace)
		except Exception as exc:
			record(f"corpus / {label}", False, f"raised {type(exc).__name__}: {exc}")
			continue

		got = [doc_key(d.metadata) for d in docs]
		want = [doc_key(r["metadata"]) for r in expected["results"]]

		if not want and not got:
			record(f"corpus / {label}", True, "both empty (filter matched nothing)")
			continue
		if got == want:
			record(f"corpus / {label}", True, f"n={len(got)} identical to Pinecone")
			continue

		# Disagreement: let exact search decide.
		exact = exact_topk(collection, translate_filter(flt),
		                   chroma.embeddings.embed_query(query), k, doc_key)
		overlap = len(set(got) & set(want))
		if exact is None:
			record(f"corpus / {label}", False,
			       f"differs from Pinecone (overlap={overlap}/{len(want)}), subset too large to arbitrate")
		elif got == exact:
			record(f"corpus / {label}", True,
			       f"differs from Pinecone (overlap={overlap}/{len(want)}) but MATCHES exact search "
			       f"-- Pinecone is the approximate one")
		else:
			record(f"corpus / {label}", False,
			       f"differs from exact search too (overlap with exact="
			       f"{len(set(got) & set(exact))}/{len(exact)})")


def check_corpus_payload(reference: dict) -> None:
	print("\n=== 3. corpus payload (page_content + metadata) ===")
	namespace = reference["provenance"]["corpus_namespace"]
	chroma = store(config.CORPUS_COLLECTION, config.CORPUS_EMBEDDING_MODEL, aliases=(namespace,))

	label, query, kwargs = cases.CORPUS_CASES[0]
	expected = reference["corpus"][label]["results"]
	docs = chroma.similarity_search(query, k=reference["k"],
	                                filter=cases.build_filter(**kwargs), namespace=namespace)
	want_by_key = {doc_key(r["metadata"]): r for r in expected}

	content_ok = meta_keys_ok = meta_values_ok = meta_order_ok = 0
	compared = 0
	for doc in docs:
		want = want_by_key.get(doc_key(doc.metadata))
		if want is None:
			continue
		compared += 1
		if doc.page_content == want["page_content"]:
			content_ok += 1
		got_meta, want_meta = norm_meta(doc.metadata), norm_meta(want["metadata"])
		if set(got_meta) == set(want_meta):
			meta_keys_ok += 1
			if all(got_meta[key] == want_meta[key] for key in got_meta):
				meta_values_ok += 1
		# Key order drives bibtex field order in __dict_to_bibtex__.
		if list(got_meta) == list(want_meta):
			meta_order_ok += 1

	record("payload / documents compared", compared > 0, f"{compared} shared documents")
	record("payload / page_content identical", compared and content_ok == compared,
	       f"{content_ok}/{compared}")
	record("payload / metadata key sets identical", compared and meta_keys_ok == compared,
	       f"{meta_keys_ok}/{compared}")
	record("payload / metadata values identical", compared and meta_values_ok == compared,
	       f"{meta_values_ok}/{compared}")
	record("payload / metadata key ORDER identical", compared and meta_order_ok == compared,
	       f"{meta_order_ok}/{compared}")

	# Show one concrete diff if anything mismatched, so failures are actionable.
	if compared and meta_values_ok < compared:
		for doc in docs:
			want = want_by_key.get(doc_key(doc.metadata))
			if not want:
				continue
			got_meta, want_meta = norm_meta(doc.metadata), norm_meta(want["metadata"])
			missing = sorted(set(want_meta) - set(got_meta))
			extra = sorted(set(got_meta) - set(want_meta))
			differing = sorted(k for k in set(got_meta) & set(want_meta)
			                   if got_meta[k] != want_meta[k])
			if missing or extra or differing:
				print(f"      first diff on {doc_key(doc.metadata)}")
				print(f"        missing in chroma : {missing[:6]}")
				print(f"        extra in chroma   : {extra[:6]}")
				for key in differing[:4]:
					print(f"        {key}: chroma={got_meta[key]!r} pinecone={want_meta[key]!r}")
				break


def check_entities(reference: dict) -> None:
	print("\n=== 4. entity retrieval (search_name reproduction) ===")
	stores = {
		namespace: store(namespace, config.ENTITY_EMBEDDING_MODEL)
		for namespace in ("field_name", "institution_name")
	}
	k = reference["k"]

	for namespace, query in cases.ENTITY_CASES:
		key = f"{namespace}::{query}"
		expected = reference["entities"].get(key)
		if expected is None:
			record(f"entity / {key}", False, "missing from reference")
			continue
		try:
			# exactly what name.py:32-33 does
			docs = stores[namespace].similarity_search(query, filter={}, k=k)
		except Exception as exc:
			record(f"entity / {key}", False, f"raised {type(exc).__name__}: {exc}")
			continue

		id_column = namespace.replace("_name", "_id")
		id_of = lambda m: norm_value(m.get(id_column))
		got = [id_of(d.metadata) for d in docs]
		want = [id_of(r["metadata"]) for r in expected["results"]]
		overlap = len(set(got) & set(want))
		if got == want:
			record(f"entity / {key}", True, f"n={len(got)} identical to Pinecone")
		else:
			exact = exact_topk(stores[namespace]._collection, None,
			                   stores[namespace].embeddings.embed_query(query), k, id_of)
			if exact is None:
				record(f"entity / {key}", False,
				       f"differs from Pinecone (overlap={overlap}/{len(want)}), not arbitrated")
			elif got == exact:
				record(f"entity / {key}", True,
				       f"differs from Pinecone (overlap={overlap}/{len(want)}) but MATCHES exact "
				       f"search -- Pinecone is the approximate one")
			else:
				record(f"entity / {key}", False,
				       f"differs from exact search too "
				       f"(overlap with exact={len(set(got) & set(exact))}/{len(exact)})")

		# The markdown search_name hands to the model must match byte for byte --
		# but only when the two backends actually returned the same rows.
		# Otherwise this would just restate the retrieval difference above.
		if got != want:
			print(f"      (markdown check skipped: different rows retrieved)")
			continue

		def markdown(metadatas):
			frame = pd.DataFrame(metadatas)
			return frame.astype(cases.TYPE_DICT[namespace]).to_markdown(floatfmt="")

		try:
			same = markdown([d.metadata for d in docs]) == markdown(
				[r["metadata"] for r in expected["results"]])
			record(f"entity / {key} / rendered markdown", same, "byte-identical tool output")
		except Exception as exc:
			record(f"entity / {key} / rendered markdown", False,
			       f"{type(exc).__name__}: {exc}")


def check_exact_recall(reference: dict) -> None:
	"""Chroma's HNSW result vs a brute-force exact search over the same vectors.

	This is the arbiter that Pinecone cannot be: Pinecone is itself approximate,
	and on some probes it is the one that misses true neighbours. Comparing
	against exact search measures our own index quality directly.
	"""
	print("\n=== 5. exact-recall self check (HNSW vs brute force) ===")
	import chromadb
	import numpy as np
	from langchain_openai import OpenAIEmbeddings

	client = chromadb.PersistentClient(path=config.CHROMA_PATH)
	probes = {
		config.INSTITUTION_COLLECTION: (
			config.ENTITY_EMBEDDING_MODEL, "institution_name",
			["Max Planck", "MIT", "Tsinghua", "Northwestern University", "Peking"],
		),
		config.FIELD_COLLECTION: (
			config.ENTITY_EMBEDDING_MODEL, "field_name",
			["computer science", "sociology", "economics"],
		),
	}

	for collection_name, (model, label_key, queries) in probes.items():
		collection = client.get_collection(collection_name)
		dump = collection.get(include=["embeddings", "metadatas"])
		matrix = np.array(dump["embeddings"])
		matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
		labels = [m[label_key] for m in dump["metadatas"]]

		embedder = OpenAIEmbeddings(model=model)
		exact_hits = 0
		for query in queries:
			vector = np.array(embedder.embed_query(query))
			exact = [labels[i] for i in np.argsort(-(matrix @ (vector / np.linalg.norm(vector))))[:10]]
			hnsw = [
				m[label_key]
				for m in collection.query(query_embeddings=[vector.tolist()], n_results=10,
				                          include=["metadatas"])["metadatas"][0]
			]
			exact_hits += exact == hnsw
		record(f"recall / {collection_name}", exact_hits == len(queries),
		       f"{exact_hits}/{len(queries)} probes match brute force exactly")


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--corpus", action="store_true")
	parser.add_argument("--entities", action="store_true")
	args = parser.parse_args()
	run_all = not (args.corpus or args.entities)

	reference = load_reference()
	prov = reference["provenance"]
	print(f"baseline: {prov['corpus_index']} ns={prov['corpus_namespace']} "
	      f"| langchain-pinecone {prov['langchain_pinecone']}")

	check_filter_translation()
	if run_all or args.corpus:
		check_corpus(reference)
		check_corpus_payload(reference)
	if run_all or args.entities:
		check_entities(reference)
	if run_all:
		check_exact_recall(reference)

	failed = [r for r in results if r[0] == FAIL]
	print(f"\n{len(results) - len(failed)}/{len(results)} passed")
	if failed:
		print("\nfailures:")
		for _, name, detail in failed:
			print(f"  - {name}: {detail}")
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
