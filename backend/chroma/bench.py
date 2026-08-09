"""Measure what the local store actually costs: resident memory and latency.

Run it the way the backend would use the store -- through the adapter, with a
real embedding call excluded from the index timing so the numbers describe the
vector search itself.

    ./.venv/bin/python bench.py
"""

from __future__ import annotations

import gc
import os
import resource
import time

from dotenv import load_dotenv

import config

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

CORPUS_QUERIES = [
	"how does team size affect scientific innovation",
	"citation dynamics and sleeping beauties",
	"peer review bias in grant funding",
	"interdisciplinary research impact",
	"gender disparities in authorship",
]
ENTITY_QUERIES = ["Northwestern University", "MIT", "Tsinghua", "Max Planck", "Peking"]


def rss_mb() -> float:
	return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def directory_mb(path: str) -> float:
	total = 0
	for root, _, files in os.walk(path):
		for name in files:
			try:
				total += os.path.getsize(os.path.join(root, name))
			except OSError:
				pass
	return total / 1024 / 1024


def time_queries(store, queries, repeats: int = 3) -> tuple[float, float]:
	"""Return (cold first-query ms, warm mean ms).

	The first query against a collection pays to load its HNSW graph off disk.
	A long-running backend pays that once at startup, so the warm number is the
	one that describes steady-state serving.
	"""
	# Embed up front so the timing measures the index, not the OpenAI round trip.
	vectors = [store.embeddings.embed_query(q) for q in queries]
	collection = store._collection

	start = time.perf_counter()
	collection.query(query_embeddings=[vectors[0]], n_results=10, include=["metadatas"])
	cold = (time.perf_counter() - start) * 1000

	start = time.perf_counter()
	for _ in range(repeats):
		for vector in vectors:
			collection.query(query_embeddings=[vector], n_results=10, include=["metadatas"])
	warm = (time.perf_counter() - start) / (repeats * len(vectors)) * 1000
	return cold, warm


def main() -> None:
	import factory

	baseline = rss_mb()
	print(f"store on disk        : {directory_mb(config.CHROMA_PATH):8.1f} MB")
	print(f"baseline process RSS : {baseline:8.1f} MB")

	corpus = factory.make_corpus_store()
	entities = factory.make_entity_stores()

	measured = [
		("corpus", config.CORPUS_COLLECTION, 3072, time_queries(corpus, CORPUS_QUERIES)),
		("institutions", config.INSTITUTION_COLLECTION, 1536,
		 time_queries(entities[config.INSTITUTION_COLLECTION], ENTITY_QUERIES)),
		("fields", config.FIELD_COLLECTION, 1536,
		 time_queries(entities[config.FIELD_COLLECTION], ["sociology", "economics"])),
	]
	gc.collect()
	loaded = rss_mb()

	print(f"RSS with all indexes : {loaded:8.1f} MB   (+{loaded - baseline:.1f} MB)")
	print()
	print(f"{'collection':<14}{'rows x dim':>18}{'cold':>10}{'warm':>10}")
	for label, name, dim, (cold, warm) in measured:
		rows = config.EXPECTED_COUNTS[name]
		print(f"{label:<14}{f'{rows:,} x {dim}':>18}{cold:>8.1f}ms{warm:>8.2f}ms")

	warm_corpus = measured[0][3][1]
	print()
	print("cold = first query after start (loads the HNSW graph off disk, paid once)")
	print("warm = steady state, which is what a long-running backend sees")
	print()
	print(f"one search_literature call = 3-5 HyDE queries "
	      f"= {warm_corpus * 3:.1f}-{warm_corpus * 5:.1f} ms of vector search")


if __name__ == "__main__":
	main()
