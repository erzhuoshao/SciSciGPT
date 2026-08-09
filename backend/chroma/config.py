"""Shared configuration for the local Chroma vector store.

Everything is overridable through the environment so that nothing here has to
be edited when wiring this into the backend.
"""

from __future__ import annotations

import os

# ── where the store lives ─────────────────────────────────────────────────
# Defaults to ./store next to this file; override with CHROMA_PATH.
CHROMA_PATH = os.getenv(
	"CHROMA_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
)

# ── collections (Chroma names must be 3-512 chars of [a-zA-Z0-9._-]) ──────
CORPUS_COLLECTION = os.getenv("CHROMA_CORPUS_COLLECTION", "sciscicorpus")
FIELD_COLLECTION = os.getenv("CHROMA_FIELD_COLLECTION", "field_name")
INSTITUTION_COLLECTION = os.getenv("CHROMA_INSTITUTION_COLLECTION", "institution_name")

# ── HuggingFace sources, pinned exactly as the original notebooks pinned ──
# Both datasets were renamed from the `ErzhuoShao` org to `cssi`.
CORPUS_REPO = "cssi/SciSciGPT-SciSciCorpus"
CORPUS_REVISION = "475c99a8c2afab3c6a7e2e936d8b44c0137437b3"
CORPUS_FILES = ["data/train-00000-of-00002.parquet", "data/train-00001-of-00002.parquet"]

SCISCINET_REPO = "cssi/SciSciGPT-SciSciNet"
SCISCINET_REVISION = "ef5553f34410575c8cab8ad209a7b11a4253b2b6"

# ── embedding models (must match what produced the stored vectors) ────────
CORPUS_EMBEDDING_MODEL = "text-embedding-3-large"   # 3072 dims
ENTITY_EMBEDDING_MODEL = "text-embedding-3-small"   # 1536 dims

# ── expected row counts; the build asserts on these ───────────────────────
# Verified against the live Pinecone index on 2026-08-09.
EXPECTED_COUNTS = {
	CORPUS_COLLECTION: 24858,
	FIELD_COLLECTION: 311,
	INSTITUTION_COLLECTION: 6969,
}

# ── HNSW ──────────────────────────────────────────────────────────────────
# Cosine, to match both Pinecone indexes. Chroma's default is l2, and getting
# this wrong produces plausible-looking but wrongly ordered results.
#
# The rest are deliberately far above Chroma's defaults
# (max_neighbors=16, ef_construction=100, ef_search=100). At the defaults,
# recall measurably degrades: the query "Max Planck" returned only 7 of the 10
# true nearest neighbours. With the values below, every probe query matched a
# brute-force exact search, at ~10 ms per query -- still ~20x faster than the
# ~200 ms Pinecone network round trip.
#
# Raising ef_search alone does not help; the graph itself has to be built with
# a higher max_neighbors / ef_construction, so changing these requires a
# rebuild, not just a collection.modify().
HNSW_CONFIG = {
	"space": "cosine",
	"max_neighbors": 32,
	"ef_construction": 400,
	"ef_search": 400,
}
HNSW_SPACE = HNSW_CONFIG["space"]

# ── known divergence between HuggingFace and the live Pinecone index ──────
# The production entity index was NOT built by the committed notebook: it uses
# UUID vector ids, carries a `text` metadata field the notebook never writes,
# and stores `field_level` title-cased ("Top"/"Sub") where the pinned
# HuggingFace revision has it lower-cased ("top"/"sub").
#
# `field_level` reaches the LLM through the markdown table `search_name`
# returns. No prompt keys off its casing (grep over backend/prompts is clean),
# so this is cosmetic -- but it is a real difference, so it is a switch rather
# than a silent choice.
#
#   True  -> match the live Pinecone output exactly (default; safer for a swap)
#   False -> keep the HuggingFace values verbatim
ENTITY_FIELD_LEVEL_TITLECASE = os.getenv("CHROMA_FIELD_LEVEL_TITLECASE", "1") == "1"
