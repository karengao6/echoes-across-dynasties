"""Project sampled poets into PCA space using observable verse structure."""

import json
import math
from importlib.resources import files
from statistics import mean, pstdev

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


def principal_components(rows):
    """Return scores and variance shares for the nonzero standardized components."""
    columns = []
    for feature in zip(*rows):
        spread = pstdev(feature)
        if spread:
            center = mean(feature)
            columns.append([(value - center) / spread for value in feature])

    size = len(columns)
    covariance = [
        [sum(a * b for a, b in zip(x, y)) / len(rows) for y in columns]
        for x in columns
    ]
    vectors = [[float(i == j) for j in range(size)] for i in range(size)]

    # Jacobi rotations diagonalize the small symmetric covariance matrix.
    # Rotating the identity matrix in parallel records its eigenvectors.
    pairs = [(i, j) for i in range(size) for j in range(i + 1, size)]
    for _ in range(100 * size**2):
        if not pairs:
            break
        i, j = max(pairs, key=lambda pair: abs(covariance[pair[0]][pair[1]]))
        cross = covariance[i][j]
        if abs(cross) < 1e-12:
            break
        a, b = covariance[i][i], covariance[j][j]
        angle = math.atan2(2 * cross, b - a) / 2
        c, s = math.cos(angle), math.sin(angle)
        for k in range(size):
            if k not in (i, j):
                x, y = covariance[k][i], covariance[k][j]
                covariance[k][i] = covariance[i][k] = c * x - s * y
                covariance[k][j] = covariance[j][k] = s * x + c * y
            x, y = vectors[k][i], vectors[k][j]
            vectors[k][i], vectors[k][j] = c * x - s * y, s * x + c * y
        covariance[i][i] = c * c * a - 2 * c * s * cross + s * s * b
        covariance[j][j] = s * s * a + 2 * c * s * cross + c * c * b
        covariance[i][j] = covariance[j][i] = 0.0
    else:
        if size:
            raise ValueError("PCA failed to converge")

    eigenvalues = [covariance[i][i] for i in range(size)]
    components = [
        i for i in sorted(range(size), key=eigenvalues.__getitem__, reverse=True)
        if eigenvalues[i] > 1e-10
    ]
    total = sum(eigenvalues[i] for i in components)
    if len(components) < 2:
        raise ValueError("PCA needs at least two varying components; try a larger sample")

    # Fix the arbitrary sign of each axis using its largest absolute loading.
    scores = []
    for i in components:
        weights = [row[i] for row in vectors]
        sign = math.copysign(1, max(weights, key=abs))
        scores.append([
            sign * sum(value * weight for value, weight in zip(row, weights))
            for row in zip(*columns)
        ])
    return list(zip(*scores)), [eigenvalues[i] / total for i in components]


def poet_pca(con, manifest):
    """Load exactly the manifest's poems and project one row per poet."""
    row = con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()
    if row is None:
        raise ValueError("Database is missing its ingestion metadata")
    metadata = json.loads(row[0])
    if any(metadata[key] != manifest[key] for key in ("dataset_revision", "sources")):
        raise ValueError("Sample manifest and corpus database have different source provenance")

    poets, features = [], []
    for poet in manifest["poets"]:
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
        poets.append({
            "author": poet["author"],
            "dynasty": poet["dynasty"],
            "poemCount": len(poems),
        })

    scores, variance = principal_components(features)
    for poet, coordinates in zip(poets, scores):
        poet["scores"] = coordinates
    return {"poets": poets, "variance": variance, "features": FEATURES}


def render_page(data):
    """Embed analysis data without letting corpus text terminate the script tag."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", r"\u003c")
    template = files("echoes").joinpath("poet_pca.html").read_text(encoding="utf-8")
    return template.replace("<!-- PCA_DATA -->", payload)
