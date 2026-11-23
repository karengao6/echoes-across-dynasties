"""Build a reusable, cleaned corpus in a local SQLite file.

A "shard" is one numbered JSON file containing part of the source collection.
Here "shi" means 詩 poetry: only poet.tang.N.json and poet.song.N.json are read;
ci (詞), author biographies, and other JSON collections are outside this importer.

Author names are provisional identities within a collection. A dynasty label
means source collection, not independently verified biographical chronology.
"""

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from .text import DAMAGE, han_text, observed_form

# Match source filenames, not literary form inferred from the poem text.
SHARD = re.compile(r"poet\.(tang|song)\.[0-9]+\.json$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ingest(root: Path, db: Path, revision: str) -> dict:
    """Validate, filter and deduplicate source records, then persist poems and an audit.

    ``revision`` is the caller-supplied dataset Git commit, not this project's
    commit. Only its syntax is checked; this function does not invoke Git or
    prove the files belong to that commit. Per-file SHA-256 hashes below record
    the actual input bytes, including any local edits.

    SQLite is the handoff to sampling: later runs can query the cleaned corpus
    without parsing and deduplicating the raw JSON again. No server is needed.
    """
    if db.exists():
        raise FileExistsError(f"Refusing to overwrite {db}")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Supply the full 40-character dataset Git commit SHA")
    if not root.is_dir():
        raise ValueError(f"Source must be a dataset directory: {root}")
    # The upstream checkout documents its main shi shards in 全唐诗.
    # Also accept a directory containing shards directly, for pinned subsets.
    collection = root / "全唐诗"
    if not collection.is_dir():
        collection = root
    paths = sorted(
        path for path in collection.glob("*.json")
        if path.is_file() and SHARD.fullmatch(path.name)
    )
    if not paths:
        raise ValueError(
            "No supported poetry JSON files found; point --source at the dataset checkout"
        )
    counts = Counter()
    buckets = defaultdict(list)
    sources = []
    rejected = []
    for path in paths:
        dynasty = SHARD.fullmatch(path.name).group(1)
        raw = path.read_bytes()
        source = path.relative_to(root).as_posix()
        # The revision names the intended version; this hash fingerprints this file.
        sources.append({"path": source, "sha256": hashlib.sha256(raw).hexdigest()})
        records = json.loads(raw)
        if not isinstance(records, list):
            raise ValueError(f"Expected an array in {source}")
        for index, record in enumerate(records):
            counts["input_records"] += 1
            reason = None
            if not isinstance(record, dict):
                reason = "invalid_record"
            else:
                author, title, paragraphs = (
                    record.get(k) for k in ("author", "title", "paragraphs")
                )
                if (
                    not isinstance(author, str)
                    or not author.strip()
                    or not isinstance(title, str)
                    or not isinstance(paragraphs, list)
                    or not paragraphs
                    or not all(isinstance(x, str) for x in paragraphs)
                ):
                    reason = "invalid_schema"
                elif author.strip() in {"佚名", "無名氏", "无名氏", "不詳", "不详"}:
                    reason = "anonymous_author"
                elif DAMAGE.search("".join(paragraphs)):
                    reason = "damage_marker"
                elif not han_text("".join(paragraphs)):
                    reason = "no_han_text"
            if reason:
                counts[reason] += 1
                rejected.append({"source": source, "index": index, "reason": reason})
                continue
            text = han_text("".join(paragraphs))
            # Global content grouping prevents duplicated texts inflating similarities.
            buckets[text].append(
                {
                    "dynasty": dynasty,
                    "author": author.strip(),
                    "title": title,
                    "paragraphs": paragraphs,
                    "source": source,
                    "source_index": index,
                    "source_id": str(record.get("id", "")),
                    "form": observed_form(paragraphs),
                }
            )
    kept = []
    for text, records in sorted(buckets.items()):
        identities = {(r["dynasty"], r["author"]) for r in records}
        # An identical normalized text cannot provide independent evidence for
        # multiple poets. Exclude every disputed attribution rather than choosing one.
        if len(identities) != 1:
            counts["conflicting_attribution_records"] += len(records)
            rejected.extend(
                {
                    "source": r["source"],
                    "index": r["source_index"],
                    "reason": "conflicting_attribution",
                }
                for r in records
            )
            continue
        counts["duplicate_records"] += len(records) - 1
        # Sorted file paths and record order choose a deterministic representative.
        # Copy it so provenance remains the original source records, without cycles.
        r = {**records[0], "id": digest(text), "text": text, "provenance": records}
        kept.append(r)
    db.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A Connection context commits/rolls back but does not close the handle.
        # Close before failure cleanup, so an unsuccessful build can be removed.
        with closing(sqlite3.connect(db)) as con, con:
            con.executescript("""
                CREATE TABLE poems (
                    id TEXT PRIMARY KEY, poet_id TEXT NOT NULL, dynasty TEXT NOT NULL,
                    author TEXT NOT NULL, title TEXT NOT NULL, paragraphs TEXT NOT NULL,
                    text TEXT NOT NULL, n_chars INTEGER NOT NULL, form TEXT NOT NULL,
                    provenance TEXT NOT NULL);
                CREATE INDEX poet_index ON poems(poet_id);
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            con.executemany(
                "INSERT INTO poems VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r["id"],
                        digest(r["dynasty"] + ":" + r["author"]),
                        r["dynasty"],
                        r["author"],
                        r["title"],
                        json.dumps(r["paragraphs"], ensure_ascii=False),
                        r["text"],
                        len(r["text"]),
                        r["form"],
                        json.dumps(r["provenance"], ensure_ascii=False),
                    )
                    for r in kept
                ],
            )
            counts["retained_poems"] = len(kept)
            report = {
                "schema_version": 1,
                "source_selection": "main_shards",
                "dataset_revision": revision,
                "sources": sources,
                "counts": dict(counts),
                "rejected": rejected,
                "form_counts": dict(Counter(r["form"] for r in kept)),
            }
            con.execute("INSERT INTO metadata VALUES (?,?)", ("ingestion", json.dumps(report)))
    except BaseException:
        db.unlink(missing_ok=True)
        raise
    return report
