"""Project sampled poets into PCA space using verse structure and character frequencies."""

import json
import math
from collections import Counter
from importlib.resources import files
from statistics import mean, pstdev

import numpy as np
from opencc import OpenCC

from .sampling import select
from .text import lines

FEATURES = (
    "fraction of five-character lines",
    "fraction of seven-character lines",
    "mean line length",
    "line length standard deviation",
    "mean lines per poem",
    "mean repeated-character fraction per poem",
    "mean repeated-line fraction per poem",
)


def structural_features(poems):
    """Summarize normalized verse lines, keeping repetitions within each poem."""
    lengths = [len(line) for poem in poems for line in poem]
    texts = ["".join(poem) for poem in poems]
    return (
        lengths.count(5) / len(lengths),
        lengths.count(7) / len(lengths),
        mean(lengths),
        pstdev(lengths),
        mean(map(len, poems)),
        mean(1 - len(set(text)) / len(text) for text in texts),
        mean(1 - len(set(poem)) / len(poem) for poem in poems),
    )


def fit_components(rows, weights=None, *, standardize=False):
    """Fit weighted PCA and project each row in the original score units."""
    rows = np.asarray(rows, dtype=float)
    if weights is None:
        weights = np.ones(len(rows)) / len(rows)
    centered = rows - np.average(rows, axis=0, weights=weights)
    if standardize:
        spread = np.sqrt(np.average(centered ** 2, axis=0, weights=weights))
        varying = np.ptp(rows, axis=0) > 0
        centered = centered[:, varying] / spread[varying]

    weighted = centered * np.sqrt(weights)[:, None]
    if weighted.shape[1] > weighted.shape[0]:
        eigenvalues, directions = np.linalg.eigh(weighted @ weighted.T)
    else:
        eigenvalues, directions = np.linalg.eigh(weighted.T @ weighted)
    tolerance = eigenvalues[-1] * 1e-10 if eigenvalues.size else 0
    keep = np.flatnonzero(eigenvalues > tolerance)[::-1]
    if len(keep) < 2:
        raise ValueError("PCA needs at least two varying components; try a larger sample")

    eigenvalues = eigenvalues[keep]
    directions = directions[:, keep]
    if weighted.shape[1] > weighted.shape[0]:
        directions = (weighted.T @ directions) / np.sqrt(eigenvalues)
    largest = np.argmax(np.abs(directions), axis=0)
    directions *= np.sign(directions[largest, np.arange(len(keep))])
    return centered @ directions, eigenvalues / eigenvalues.sum(), directions


def principal_components(rows, weights=None):
    """Return scores and variance shares for the nonzero standardized components."""
    scores, variance, _ = fit_components(rows, weights, standardize=True)
    return scores.tolist(), variance.tolist()


def character_pca(counts, weights=None):
    """Fit centered PCA on characters per 1,000 Han characters."""
    coverage = Counter(char for poet in counts for char in poet)
    minimum = max(2, math.ceil(len(counts) * 0.2))
    vocabulary = sorted(char for char, count in coverage.items() if count >= minimum)

    # Use all Han characters in the denominator, including those outside the vocabulary.
    rows = []
    for poet in counts:
        total_chars = poet.total()
        rows.append([1000 * poet[char] / total_chars for char in vocabulary])
    view = {"minimumPoets": minimum, "vocabularySize": len(vocabulary)}
    try:
        scores, variance, directions = fit_components(rows, weights)
    except ValueError:
        return {**view, "unavailable": "Fewer than two varying components in this character sample."}

    loadings = []
    for direction in directions.T:
        ranked = sorted(zip(vocabulary, direction.tolist()), key=lambda item: item[1])
        loadings.append({
            "positive": [item for item in reversed(ranked[-6:]) if item[1] > 1e-10],
            "negative": [item for item in ranked[:6] if item[1] < -1e-10],
        })
    return {
        **view,
        "scores": scores.tolist(),
        "variance": variance.tolist(),
        "loadings": loadings,
    }


def poet_pca(con, manifest):
    """Fit both weighting schemes across eligible poets, using the manifest settings."""
    row = con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()
    if row is None:
        raise ValueError("Database is missing its ingestion metadata")
    metadata = json.loads(row[0])
    if any(metadata[key] != manifest[key] for key in ("dataset_revision", "sources")):
        raise ValueError("Sample manifest and corpus database have different source provenance")

    eligible = select(
        con, manifest["seed"], manifest["poets_per_dynasty"], manifest["poems_per_poet"],
        manifest["form"], all_eligible=True,
    )
    initial = {poet["poet_id"]: poet for poet in manifest["poets"]}
    if not initial.keys() <= {poet["poet_id"] for poet in eligible["poets"]}:
        raise ValueError("Sample manifest contains poets who are ineligible in this database")
    simplified = OpenCC("t2s.json")
    traditional = OpenCC("s2t.json")
    poets, features, counts = [], [], []
    for eligible_poet in eligible["poets"]:
        poet_id = eligible_poet["poet_id"]
        poet = initial.get(poet_id, eligible_poet)
        poems = []
        for poem_id in poet["poem_ids"]:
            row = con.execute(
                "SELECT paragraphs FROM poems WHERE id = ? AND poet_id = ?",
                (poem_id, poet["poet_id"]),
            ).fetchone()
            if row is None:
                raise ValueError(f"Sample poem {poem_id} is missing for {poet['author']}")
            poems.append(lines(json.loads(row[0])))
        if not poems or not all(poems):
            raise ValueError(f"No usable verse lines for a sampled poem by {poet['author']}")
        features.append(structural_features(poems))
        counts.append(Counter(char for poem in poems for line in poem for char in line))
        poets.append({
            "author": poet["author"],
            "aliases": sorted({
                simplified.convert(poet["author"]), traditional.convert(poet["author"]),
            } - {poet["author"]}),
            "selected": poet_id in initial,
            "dynasty": poet["dynasty"],
            "poemCount": len(poems),
        })

    group_sizes = Counter(poet["dynasty"] for poet in poets)
    balanced = np.array([1 / (len(group_sizes) * group_sizes[p["dynasty"]]) for p in poets])
    fits = {}
    for name, weights in (("equal", None), ("balanced", balanced)):
        scores, variance = principal_components(features, weights)
        fits[name] = {
            "structure": {"scores": scores, "variance": variance, "features": FEATURES},
            "characters": character_pca(counts, weights),
        }
    return {"poets": poets, "fits": fits}


def render_page(data):
    """Embed analysis data without letting corpus text terminate the script tag."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", r"\u003c")
    template = files("echoes").joinpath("poet_pca.html").read_text(encoding="utf-8")
    return template.replace("<!-- PCA_DATA -->", payload)
