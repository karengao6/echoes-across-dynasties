"""Hash-ranked sampling is deterministic across machines and row order."""

import hashlib
import json
import sqlite3


def rank(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def select(
    con: sqlite3.Connection, seed=42, poets_per_dynasty=25, poems_per_poet=100, form=""
) -> dict:
    if poets_per_dynasty < 1 or poems_per_poet < 1:
        raise ValueError("Sample sizes must be positive")
    if form not in {"", "uniform_5", "uniform_7", "mixed"}:
        raise ValueError("Unknown observed form")
    rows = con.execute("SELECT id, poet_id, dynasty, author, form FROM poems ORDER BY id")
    poets = {}
    for poem_id, poet_id, dynasty, author, observed in rows:
        if form and observed != form:
            continue
        entry = poets.setdefault(
            poet_id, {"poet_id": poet_id, "dynasty": dynasty, "author": author, "poems": []}
        )
        entry["poems"].append(poem_id)
    selected = []
    for dynasty in ("tang", "song"):
        eligible = [
            p
            for p in poets.values()
            if p["dynasty"] == dynasty and len(p["poems"]) >= poems_per_poet
        ]
        if len(eligible) < poets_per_dynasty:
            raise ValueError(f"{dynasty}: {len(eligible)} eligible poets; need {poets_per_dynasty}")
        for poet in sorted(eligible, key=lambda p: rank(seed, p["poet_id"]))[:poets_per_dynasty]:
            selected.append(
                {
                    "poet_id": poet["poet_id"],
                    "author": poet["author"],
                    "dynasty": dynasty,
                    "available_poems": len(poet["poems"]),
                    "poem_ids": sorted(poet["poems"], key=lambda x: rank(seed, x))[:poems_per_poet],
                }
            )
    metadata = json.loads(
        con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()[0]
    )
    return {
        "seed": seed,
        "poets_per_dynasty": poets_per_dynasty,
        "poems_per_poet": poems_per_poet,
        "form": form,
        "dataset_revision": metadata["dataset_revision"],
        "sources": metadata["sources"],
        "poets": selected,
    }
