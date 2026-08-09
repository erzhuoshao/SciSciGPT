"""Rebuild the SciSciGPT vector store locally in Chroma, from HuggingFace.

Two sources, pinned to the same revisions the original notebooks pinned:

  * ``cssi/SciSciGPT-SciSciCorpus``  -> the literature corpus.
    This dataset *ships its own ``embedding`` column*, and those vectors were
    verified to be the ones actually serving in Pinecone (cosine 1.0000000000,
    max elementwise delta 1.8e-09 -- pure float32 storage rounding). They are
    reused verbatim, so no re-embedding is needed and retrieval is bit-faithful.

  * ``cssi/SciSciGPT-SciSciNet``     -> field / institution names.
    No embeddings ship with these, so the names are re-embedded with the same
    model the live index used (``text-embedding-3-small``).

Document/metadata layout mirrors what ``langchain_pinecone`` returns today, so
``literature.py`` and ``name.py`` see byte-identical inputs:

  * ``page_content`` <- the ``text`` metadata field (Pinecone's ``text_key``)
  * ``metadata``     <- everything else

Usage::

    python build_index.py                 # build everything
    python build_index.py --only corpus
    python build_index.py --only entities
    python build_index.py --reset         # drop existing collections first
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

import config

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


# ── metadata shaping ──────────────────────────────────────────────────────
# Copied verbatim from backend/SciSciCorpus.ipynb so the stored metadata is
# identical to what was upserted into Pinecone. Do not "clean this up" --
# every quirk here (the per-author boolean keys, the 25k truncation, the
# year derived from date) is visible to the LLM through __dict_to_bibtex__.
def filter_nan(d):
	d2 = {}
	for k, v in d.items():
		if k in ["section_summary", "abstract", "section_text_token_count"]:
			continue
		if k in ["section_text"]:
			d2["text"] = v[:25000]
			continue
		if k == "section_id":
			d2["section_id"] = int(v)
			continue

		if k == "date":
			if type(v) == str:
				d2["date"] = v
				d2["year"] = int(v.split("-")[0])
			continue

		if k == "author":
			if type(v) == str:
				d2["author"] = v
				authors = v.split(" and ")
				for i in authors:
					author_name = " ".join(i.split(", ")[::-1])
					d2["author: {}".format(author_name)] = True
			continue

		if k == "embedding":
			d2[k] = v
			continue

		if k in ["urldate", "number"]:
			continue

		if pd.isna(v):
			continue
		else:
			d2[k] = v

		if k == "authors":
			d2["authors"] = [" ".join(i.split(", ")[::-1]) for i in v.split(" and ")]
	return d2


def sanitize(metadata: dict) -> dict:
	"""Chroma metadata values must be str / int / float / bool. Drop the rest."""
	out = {}
	for key, value in metadata.items():
		if value is None:
			continue
		if isinstance(value, bool):
			out[key] = value
		elif isinstance(value, (int, float, str)):
			# NaN would survive isinstance(float) but is not a useful filter value
			if isinstance(value, float) and pd.isna(value):
				continue
			out[key] = value
		elif hasattr(value, "item"):
			out[key] = value.item()
		elif isinstance(value, (list, tuple)):
			out[key] = ", ".join(str(v) for v in value)
		else:
			out[key] = str(value)
	return out


# ── chroma helpers ────────────────────────────────────────────────────────

def get_client():
	import chromadb

	os.makedirs(config.CHROMA_PATH, exist_ok=True)
	return chromadb.PersistentClient(path=config.CHROMA_PATH)


def make_collection(client, name: str, reset: bool):
	if reset:
		try:
			client.delete_collection(name)
			print(f"  dropped existing collection {name!r}")
		except Exception:
			pass
	return client.get_or_create_collection(
		name=name,
		configuration={"hnsw": dict(config.HNSW_CONFIG)},
		embedding_function=None,  # vectors are always supplied explicitly
	)


# Chroma rejects a single add() larger than 5461 rows (SQLite variable limit),
# so every flush is chunked regardless of how much the caller accumulated.
MAX_ADD = 2000


def flush(collection, ids, embeddings, documents, metadatas):
	if not ids:
		return
	for i in range(0, len(ids), MAX_ADD):
		stop = i + MAX_ADD
		collection.add(
			ids=ids[i:stop],
			embeddings=embeddings[i:stop],
			documents=documents[i:stop],
			metadatas=metadatas[i:stop],
		)
	ids.clear(); embeddings.clear(); documents.clear(); metadatas.clear()


# ── corpus ────────────────────────────────────────────────────────────────

def build_corpus(client, reset: bool, add_batch: int = 512):
	print(f"\n[corpus] {config.CORPUS_REPO} @ {config.CORPUS_REVISION[:8]}")
	collection = make_collection(client, config.CORPUS_COLLECTION, reset)

	paths = []
	for filename in config.CORPUS_FILES:
		print(f"  fetching {filename} ...")
		paths.append(
			hf_hub_download(
				repo_id=config.CORPUS_REPO,
				filename=filename,
				revision=config.CORPUS_REVISION,
				repo_type="dataset",
			)
		)

	ids, embeddings, documents, metadatas = [], [], [], []
	seen: set[str] = set()
	total = skipped = 0

	for path in paths:
		parquet = pq.ParquetFile(path)
		for record_batch in parquet.iter_batches(batch_size=256):
			for record in record_batch.to_pylist():
				metadata = filter_nan(record)

				vector = metadata.pop("embedding", None)
				if vector is None:
					skipped += 1
					continue
				# Pinecone's text_key: `text` becomes page_content, not metadata.
				text = metadata.pop("text", "")
				url = metadata.get("url")
				section_id = metadata.get("section_id")
				if url is None or section_id is None:
					skipped += 1
					continue

				doc_id = f"{url}::{section_id}"
				if doc_id in seen:
					skipped += 1
					continue
				seen.add(doc_id)

				ids.append(doc_id)
				embeddings.append([float(x) for x in vector])
				documents.append(text)
				metadatas.append(sanitize(metadata))
				total += 1

				if len(ids) >= add_batch:
					flush(collection, ids, embeddings, documents, metadatas)
					print(f"    ... {total:,} indexed", end="\r", flush=True)

	flush(collection, ids, embeddings, documents, metadatas)
	print(f"    {total:,} indexed, {skipped} skipped" + " " * 20)
	return collection


# ── entities ──────────────────────────────────────────────────────────────

def build_entities(client, reset: bool, embed_batch: int = 128):
	from langchain_openai import OpenAIEmbeddings

	embedder = OpenAIEmbeddings(model=config.ENTITY_EMBEDDING_MODEL)

	specs = [
		("fields.parquet", config.FIELD_COLLECTION, "field_id", "field_name"),
		("institutions.parquet", config.INSTITUTION_COLLECTION, "institution_id", "institution_name"),
	]

	built = []
	for filename, collection_name, id_column, name_column in specs:
		print(f"\n[{collection_name}] {config.SCISCINET_REPO} @ {config.SCISCINET_REVISION[:8]}")
		collection = make_collection(client, collection_name, reset)

		path = hf_hub_download(
			repo_id=config.SCISCINET_REPO,
			filename=filename,
			revision=config.SCISCINET_REVISION,
			repo_type="dataset",
		)
		rows = pq.read_table(path).to_pylist()
		names = [str(row[name_column]) for row in rows]

		print(f"  embedding {len(names):,} names with {config.ENTITY_EMBEDDING_MODEL} ...")
		vectors = []
		for i in range(0, len(names), embed_batch):
			vectors += embedder.embed_documents(names[i : i + embed_batch])
			print(f"    ... {min(i + embed_batch, len(names)):,}/{len(names):,}", end="\r", flush=True)

		ids, embeddings, documents, metadatas = [], [], [], []
		for row, name, vector in zip(rows, names, vectors):
			metadata = {k: v for k, v in row.items() if v is not None}
			# See config.ENTITY_FIELD_LEVEL_TITLECASE: the live index stores
			# "Top"/"Sub", the pinned HuggingFace revision stores "top"/"sub".
			if config.ENTITY_FIELD_LEVEL_TITLECASE and isinstance(metadata.get("field_level"), str):
				metadata["field_level"] = metadata["field_level"].title()
			ids.append(str(row[id_column]))
			embeddings.append(vector)
			documents.append(name)  # matches Pinecone's popped `text` field
			metadatas.append(sanitize(metadata))
		flush(collection, ids, embeddings, documents, metadatas)
		print(f"    {len(names):,} indexed" + " " * 20)
		built.append(collection)
	return built


# ── verification ──────────────────────────────────────────────────────────

def verify(client) -> bool:
	print("\n[verify] collection counts")
	ok = True
	for name, expected in config.EXPECTED_COUNTS.items():
		try:
			actual = client.get_collection(name).count()
		except Exception as exc:
			print(f"  {name:<20} MISSING ({type(exc).__name__})")
			ok = False
			continue
		mark = "OK " if actual == expected else "BAD"
		if actual != expected:
			ok = False
		print(f"  {mark} {name:<20} {actual:>7,} / {expected:,} expected")
	return ok


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--only", choices=["corpus", "entities"], help="build a single source")
	parser.add_argument("--reset", action="store_true", help="drop existing collections first")
	parser.add_argument("--verify-only", action="store_true", help="only check counts")
	args = parser.parse_args()

	client = get_client()
	print(f"chroma store: {config.CHROMA_PATH}")

	if not args.verify_only:
		if args.only in (None, "corpus"):
			build_corpus(client, args.reset)
		if args.only in (None, "entities"):
			build_entities(client, args.reset)

	ok = verify(client)
	print("\n" + ("BUILD OK" if ok else "BUILD FAILED: counts do not match"))
	return 0 if ok else 1


if __name__ == "__main__":
	sys.exit(main())
