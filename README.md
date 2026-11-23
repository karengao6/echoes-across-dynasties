# Echoes Across Dynasties

Auditable corpus ingestion, deterministic cohort selection, and an interactive
poet-style PCA page.
Read `docs/research-design.md` before extracting features.

## Run on macOS / Apple Silicon

Install uv, then from this directory:

```bash
uv sync
uv run pytest
# Download separately; corpus data are not bundled with this starter.
git clone --depth 1 https://github.com/chinese-poetry/chinese-poetry.git data/raw/chinese-poetry
git -C data/raw/chinese-poetry rev-parse HEAD
```

Copy the printed full commit SHA into REVISION below:

```bash
uv run echoes ingest --source data/raw/chinese-poetry --revision REVISION
uv run echoes sample --config configs/corpus.toml
uv run echoes pca
```

`uv.lock` is included. Use `uv sync --locked` to reproduce the tested environment.
The Python pipeline uses only the standard library; development tools are locked separately.

Outputs:
- `data/poetry.sqlite`: source paragraphs, normalized searchable Han text, provisional poet
  identifiers, observed form, and all retained duplicate provenance.
- `outputs/quality.json`: source hashes, revision, counts, rejected-record locations.
- `outputs/subset.json`: selected poet IDs and exact sampled poem IDs.
- `outputs/poet-style.html`: self-contained PCA scatterplot. Open the file in a
  browser, select the two axes, and hover over or focus a point for poet details.
  The current baseline uses verse structure from the sampled poems. A cohort needs
  at least two nonzero principal components to generate the page.
- `outputs/data-cleaning.html`: linked companion page with cleaning counts,
  eligibility by poem cutoff, sampling limitations, and the feature rationale.

To regenerate from a database created by an older importer, use a fresh database
path for ingestion and pass that same `--db` to `sample` and `pca`.

SQLite is a local file, not a database service. It stores the cleaned corpus once
so sampling can reuse it without rereading and deduplicating all the source JSON.
A **shard** is simply one numbered file containing part of the collection; **shi**
means 詩 poetry in this importer's source-file convention.

`--revision` identifies the **dataset repository's** commit for reproducibility.
The importer checks that it looks like a full SHA, but does not verify Git state.
Use an unmodified checkout at that commit. Each imported file also gets a SHA-256
hash in the audit report, recording its actual bytes even if locally edited.

The importer reads `poet.tang.NUMBER.json` and `poet.song.NUMBER.json` directly
inside `全唐诗` when given an upstream checkout. You can also point it to a
flat directory of shards. Nested directories such as `error` are skipped.
It requires string author/title and an array of string paragraphs. Paragraph entries
can contain multiple verse lines, so punctuation is split before measuring form.
The schema was checked against an upstream Tang shard; run against your pinned
checkout to verify every file rather than assuming the entire corpus is uniform.

Default: 25 poets per source collection, each with 100 distinct clean poems.
Selection is hash-ranked with a fixed seed, not ranked by fame or phrase frequency.
The command fails clearly if either collection lacks enough eligible poets.
Use `form = "uniform_5"` for a controlled five-character-line cohort; rebuild a
separate sample manifest for each design. Counts are equalized, character budgets
are not: add length matching in the baseline stage.

Source text remains unchanged. Normalized text uses NFC and retains Han characters;
no script conversion or historical spelling correction occurs. Search examples must
therefore use corpus spelling (e.g. 秋風 rather than 秋风). Unicode Han detection
uses broad codepoint ranges and is not a linguistic word segmenter.
Known damage markers and anonymous names are excluded. These checks are heuristics,
not complete textual authentication. Punctuation-insensitive identical text is
collapsed within an attribution; text assigned to multiple identities is excluded
and reported. Near-duplicates, title variants, aliases, annotation artifacts, and
biographical dates still require review. A poet identity is collection + author name.

Importer is intended for a local laptop, not streaming-scale use: it holds records
and deduplication buckets in memory and reads one JSON shard at a time. No model
weights or corpus download happen inside the code. Ingest refuses an existing DB.
Inspect the quality report before building the primary cohort.

## Current files

```text
configs/corpus.toml
src/echoes/text.py        # normalization, verse splitting, measured form
src/echoes/corpus.py      # ingestion, quality audit, SQLite
src/echoes/sampling.py    # fixed-size, reproducible cohort
src/echoes/cli.py         # command line entrypoints
src/echoes/stylometry.py  # structural features and PCA
src/echoes/poet_pca.html  # interactive scatterplot template
 tests/test_corpus.py     # normalization, deduplication, provenance, sampling
 docs/research-design.md  # representations, controls, evaluation, roadmap
```

Future modules: `features/`, `embeddings/`, `similarity/`, `evaluation/`,
`backend/`, and a separate `frontend/` React application. Add these only as their
milestones are implemented. Upstream licensing and redistribution terms should be
reviewed before publishing a corpus derivative; no upstream poetry data are bundled.

## Verification at delivery

Run `uv run pytest` and `uv run ruff check src tests` for the current verification suite. A smoke ingestion of the upstream
1,000-record first Tang shard retained 724 poems, excluded 256 anonymous records,
3 damaged records and 16 conflicting-attribution records, and collapsed one duplicate.
This is a schema smoke check, not full-corpus validation or a literary assessment.
The smoke run used a placeholder revision and temporary database; it is not a
research dataset or a reproducible experimental result. Run against a pinned checkout.
