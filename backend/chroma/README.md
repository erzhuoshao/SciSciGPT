# Local Chroma vector store

A drop-in replacement for the two Pinecone indexes, rebuilt from HuggingFace
and served from disk on the same machine as the backend.

Nothing outside this directory is modified. Wiring it into `literature.py` and
`name.py` is a separate, deliberate step -- see [Integration](#integration).

## Why local

All figures below are measured on this machine by `bench.py`, not estimated.

| | Pinecone (today) | Local Chroma |
|---|---|---|
| Corpus query, steady state | ~200 ms (network round trip) | **29.6 ms** |
| Per literature call (3-5 HyDE queries, serial) | 0.6-1.0 s | **89-148 ms** |
| Entity query (`search_name`) | ~200 ms | **4.5 ms** |
| Cost | $1-3 / month | $0 |
| Resident memory | -- | **+533 MB** |
| Disk | -- | **956 MB** |
| Cold start (once, at process start) | -- | 984 ms |
| External dependency | yes | none |

So roughly a **7x latency improvement** end to end, not the order-of-magnitude a
raw HNSW micro-benchmark suggests: the tuned recall settings and the metadata
read are most of the 29.6 ms, and both are load-bearing.

The backend already runs on a single machine behind ngrok, so co-locating the
vector store adds no new failure mode: if the machine is down, SciSciGPT is
down regardless of where the vectors live. Pinecone, being external, is
currently an *additional* failure point (network, API outage, key rotation).

## Data provenance

Everything is rebuilt from HuggingFace at pinned revisions -- the same ones the
original notebooks pinned, adjusted for the `ErzhuoShao` -> `cssi` org rename.

| Collection | Source | Revision | Rows | Vectors |
|---|---|---|---|---|
| `sciscicorpus` | `cssi/SciSciGPT-SciSciCorpus` | `475c99a8` | 24,858 | shipped with the dataset |
| `field_name` | `cssi/SciSciGPT-SciSciNet` `fields.parquet` | `ef5553f3` | 311 | re-embedded |
| `institution_name` | `cssi/SciSciGPT-SciSciNet` `institutions.parquet` | `ef5553f3` | 6,969 | re-embedded |

Row counts were verified against the live Pinecone indexes and match exactly
(24,858 / 311 / 6,969).

**The corpus is not re-embedded.** The HuggingFace dataset ships an `embedding`
column, and those vectors were verified to be the ones actually serving in
Pinecone:

```
cosine similarity = 1.0000000000
max elementwise delta = 1.8e-09      (float32 storage rounding)
```

So the corpus is bit-faithful to production and costs $0 to rebuild. This also
means cell 2 of `SciSciCorpus.ipynb` is dead code: `documents` is built in
cell 1 from the dataset's own `embedding` column, so the recomputed embeddings
assigned to `sciscicorpus["embedding"]` are never read.

Only the 7,280 entity names are re-embedded (`text-embedding-3-small`, ~$0.002).

## Usage

```bash
cd backend/chroma
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

./.venv/bin/python build_index.py --reset      # build all three collections
./.venv/bin/python build_index.py --verify-only
./.venv/bin/python test_parity.py              # A/B against live Pinecone
```

`build_index.py` asserts the final row counts and exits non-zero on mismatch.
This guards against the `[:100]` debug truncation still present in
`SciSciCorpus.ipynb`, which silently produces a 100-row corpus.

Store location defaults to `./store`, overridable with `CHROMA_PATH`.

## Files

| File | Purpose |
|---|---|
| `config.py` | Paths, collection names, pinned revisions, HNSW tuning, expected counts |
| `chroma_vs.py` | `ChromaVectorStore` -- the `VectorStore` adapter |
| `build_index.py` | Rebuild all collections from HuggingFace |
| `factory.py` | `make_corpus_store()` / `make_entity_stores()` / `health()` |
| `cases.py` | Test cases shared by the dumper and the checker |
| `dump_pinecone_reference.py` | Capture the live Pinecone baseline (**run in the production env**) |
| `test_parity.py` | Offline A/B against that baseline |
| `bench.py` | Measure resident memory and query latency |

The parity workflow is deliberately split in two so the baseline is captured
with the exact `langchain-pinecone` version currently serving, while the check
itself runs in this directory's venv and needs no Pinecone access:

```bash
conda activate sciscigpt && python dump_pinecone_reference.py   # -> reference.json
./.venv/bin/python test_parity.py
```

## HNSW tuning

Chroma's defaults (`max_neighbors=16`, `ef_construction=100`, `ef_search=100`)
lose measurable recall at this scale. The probe query `"Max Planck"` returned
only **7 of the 10** true nearest neighbours.

`config.HNSW_CONFIG` raises this to `max_neighbors=32`, `ef_construction=400`,
`ef_search=400`, at which every probe query matches a brute-force exact search,
costing ~10 ms per query -- still ~20x faster than Pinecone's ~200 ms round trip.

Two things worth knowing:

* **Raising `ef_search` alone does not help.** The graph itself has to be built
  with a higher `max_neighbors` / `ef_construction`, so changing these requires
  a rebuild, not a `collection.modify()`.
* **Pinecone is approximate too.** On the `MIT` and `Tsinghua` probes it is
  Pinecone that misses true neighbours while the tuned Chroma index matches
  brute force exactly. This is why `test_parity.py` also runs an exact-recall
  self check (section 5) rather than treating Pinecone as ground truth.

## Known divergence: the live index is not built from this HuggingFace revision

The production *entity* index was not produced by the committed
`SciSciNet-Vector.ipynb`. Evidence:

| | committed notebook / pinned HF revision | live Pinecone index |
|---|---|---|
| vector id | `str(institution_id)` | UUID |
| `text` metadata key | not written | present (= the name) |
| `field_level` | `top` / `sub` | `Top` / `Sub` |

Only the third one is visible to the model, through the markdown table
`search_name` returns. No prompt keys off its casing, so it is cosmetic -- but
it is a genuine source difference, so it is a switch rather than a silent
choice:

```python
# config.py
ENTITY_FIELD_LEVEL_TITLECASE = os.getenv("CHROMA_FIELD_LEVEL_TITLECASE", "1") == "1"
```

Default `1` matches the live Pinecone output exactly. Set
`CHROMA_FIELD_LEVEL_TITLECASE=0` to keep the HuggingFace values verbatim.

## Behaviour reproduced from Pinecone

`langchain_pinecone` pops the `text` metadata key into `page_content`
(`vectorstores.py:348-352`). The build mirrors this exactly:

* **corpus** -- `page_content` = `section_text[:25000]`, `metadata` = everything
  else, including the per-author `"author: <Name>": True` keys that
  `__dict_to_bibtex__` surfaces to the LLM.
* **entities** -- `page_content` = the name, `metadata` = the parquet row.

`filter_nan()` is copied verbatim from `SciSciCorpus.ipynb` so the stored
metadata is identical, quirks included.

### Filter dialect differences

Chroma's filter dialect is nearly identical to Pinecone's, but three
differences are reachable from the current call sites. `translate_filter()`
handles all three.

| Case | Pinecone | Chroma | Where it comes from |
|---|---|---|---|
| Single condition | `{"$and": [c]}` works | **rejects** `$and` with < 2 operands | `literature.py:142` whenever exactly one constraint is set |
| No filter | `{}` works | **rejects** empty `where` | `name.py:32` sends `json.loads("{}")` on *every* call |
| numpy scalars | tolerated | rejected | pandas-derived filter values |

Both rejections are hard errors, not silent degradations -- without the
translator, `search_name` would fail on every single invocation.

### Distance metric

Collections are created with `hnsw:space = cosine` to match both Pinecone
indexes. **Chroma's default is `l2`.** Getting this wrong does not raise; it
silently returns plausible-looking results in the wrong order.

### Namespace handling

`namespace` maps to a Chroma collection. An unrecognised namespace raises
rather than silently searching the wrong collection.

## Integration

Not wired in yet, by design. When you are ready, the change is two
initialisation blocks; no retrieval logic moves.

`backend/tools/literature.py:288`

```python
vs = PineconeVectorStore.from_existing_index(
    embedding=OpenAIEmbeddings(model="text-embedding-3-large", api_key=openai_api_key),
    index_name=sciscicorpus_index,
    namespace=sciscicorpus_namespace,
)
```

`backend/tools/name.py:64-70`

```python
vectorstore_dict = {
    namespace: PineconeVectorStore.from_existing_index(
        embedding=OpenAIEmbeddings(model="text-embedding-3-small"),
        namespace=namespace,
        index_name=os.getenv("NAME_SEARCH_INDEX"),
    ) for namespace in ["field_name", "institution_name"]
}
```

Everything downstream -- `__search_and_format__`, `_author_match`, the HyDE
chains, `__dict_to_bibtex__` -- consumes `Document.page_content` and
`Document.metadata` and does not change.

### Before merging into `backend/requirements.txt`

`chromadb` upgrades `aiohttp` 3.9.5 -> 3.14.x and installs `uvloop`, which
uvicorn auto-selects when importable -- that changes the production event loop.
See the note at the top of `requirements.txt`.

## Verification status

`test_parity.py` -- **36/36 passing**. Highlights:

* corpus `page_content`, metadata keys, metadata values and **metadata key
  order** are all identical to what Pinecone returns
* `search_name`'s rendered markdown is byte-identical
* every probe query matches a brute-force exact search

Three cases return *different* documents from Pinecone (`corpus / abstract
only`, `institution_name / MIT`, `institution_name / Tsinghua`). In all three,
brute-force search confirms **Chroma is right and Pinecone is the one that
drifts** -- these are near-ties (one measured gap: 0.416245 vs 0.416207). That
is why the test arbitrates with exact search instead of treating Pinecone as
ground truth.

## Operational notes

* **Disk** is the binding constraint, not memory. The store is 956 MB and the
  root filesystem was at 83% before the build.
* **Backups**: the store is disposable. Recover either by re-running
  `build_index.py` (~$0.002, corpus vectors come from HuggingFace) or by
  archiving `store/` to the existing GCS bucket.
* **Concurrency**: reads only; the backend runs a single uvicorn worker
  (`deploy/sciscigpt-backend.service` passes no `--workers`), so the index is
  loaded once, not per worker.
* After a successful build, `~/.cache/huggingface` (~900 MB of parquet) can be
  deleted.
