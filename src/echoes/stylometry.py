"""Project sampled poets into PCA space using verse structure and character frequencies."""

import json
import math
from collections import Counter
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

    covariance = [
        [sum(a * b for a, b in zip(x, y)) / len(rows) for y in columns]
        for x in columns
    ]
    eigenvalues, vectors = symmetric_eigenvectors(covariance)
    components = ranked_components(eigenvalues)
    total = sum(eigenvalues[i] for i in components)

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


def symmetric_eigenvectors(matrix):
    """Diagonalize a small symmetric matrix in place; return column eigenvectors."""
    size = len(matrix)
    vectors = [[float(i == j) for j in range(size)] for i in range(size)]

    # Jacobi rotations diagonalize the small symmetric matrix matrix.
    # Rotating the identity matrix in parallel records its eigenvectors.
    pairs = [(i, j) for i in range(size) for j in range(i + 1, size)]
    for _ in range(100 * size**2):
        if not pairs:
            break
        i, j = max(pairs, key=lambda pair: abs(matrix[pair[0]][pair[1]]))
        cross = matrix[i][j]
        if abs(cross) < 1e-12:
            break
        a, b = matrix[i][i], matrix[j][j]
        angle = math.atan2(2 * cross, b - a) / 2
        c, s = math.cos(angle), math.sin(angle)
        for k in range(size):
            if k not in (i, j):
                x, y = matrix[k][i], matrix[k][j]
                matrix[k][i] = matrix[i][k] = c * x - s * y
                matrix[k][j] = matrix[j][k] = s * x + c * y
            x, y = vectors[k][i], vectors[k][j]
            vectors[k][i], vectors[k][j] = c * x - s * y, s * x + c * y
        matrix[i][i] = c * c * a - 2 * c * s * cross + s * s * b
        matrix[j][j] = s * s * a + 2 * c * s * cross + c * c * b
        matrix[i][j] = matrix[j][i] = 0.0
    else:
        if size:
            raise ValueError("PCA failed to converge")

    return [matrix[i][i] for i in range(size)], vectors


def ranked_components(eigenvalues):
    components = sorted(range(len(eigenvalues)), key=eigenvalues.__getitem__, reverse=True)
    tolerance = max(eigenvalues, default=0) * 1e-10
    components = [i for i in components if eigenvalues[i] > tolerance]
    if len(components) < 2:
        raise ValueError("PCA needs at least two varying components; try a larger sample")
    return components


def character_pca(counts):
    """Fit centered PCA on characters per 1,000 Han characters."""
    coverage = Counter(char for poet in counts for char in poet)
    minimum = max(2, math.ceil(len(counts) * 0.2))
    vocabulary = sorted(char for char, count in coverage.items() if count >= minimum)

    # Use all Han characters in the denominator, including those outside the vocabulary.
    rows = []
    for poet in counts:
        total_chars = poet.total()
        rows.append([1000 * poet[char] / total_chars for char in vocabulary])
    centers = [mean(column) for column in zip(*rows)]
    centered = [[value - center for value, center in zip(row, centers)] for row in rows]

    # With many more characters than poets, diagonalize XXᵀ in poet space.
    # For eigenvector u and eigenvalue λ, Xᵀu/√λ gives the character weights.
    gram = [[0.0] * len(rows) for _ in rows]
    for i, row in enumerate(centered):
        for j in range(i + 1):
            gram[i][j] = gram[j][i] = sum(a * b for a, b in zip(row, centered[j]))
    eigenvalues, vectors = symmetric_eigenvectors(gram)
    view = {"minimumPoets": minimum, "vocabularySize": len(vocabulary)}
    try:
        components = ranked_components(eigenvalues)
    except ValueError:
        return {**view, "unavailable": "Fewer than two varying components in this character sample."}

    total = sum(eigenvalues[i] for i in components)
    scores, loadings = [], []
    columns = list(zip(*centered))
    for i in components:
        scale = math.sqrt(eigenvalues[i])
        direction = [row[i] for row in vectors]
        weights = [sum(a * b for a, b in zip(col, direction)) / scale for col in columns]
        sign = math.copysign(1, max(weights, key=abs))
        scores.append([sign * scale * value for value in direction])
        ranked = sorted(zip(vocabulary, (sign * w for w in weights)), key=lambda item: item[1])
        loadings.append({
            "positive": [item for item in reversed(ranked[-6:]) if item[1] > 1e-10],
            "negative": [item for item in ranked[:6] if item[1] < -1e-10],
        })
    return {
        **view,
        "scores": list(zip(*scores)),
        "variance": [eigenvalues[i] / total for i in components],
        "loadings": loadings,
    }


def poet_pca(con, manifest):
    """Load exactly the manifest's poems and project one row per poet."""
    row = con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()
    if row is None:
        raise ValueError("Database is missing its ingestion metadata")
    metadata = json.loads(row[0])
    if any(metadata[key] != manifest[key] for key in ("dataset_revision", "sources")):
        raise ValueError("Sample manifest and corpus database have different source provenance")

    poets, features, counts = [], [], []
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
        counts.append(Counter(char for poem in poems for line in poem for char in line))
        poets.append({
            "author": poet["author"],
            "dynasty": poet["dynasty"],
            "poemCount": len(poems),
        })

    scores, variance = principal_components(features)
    return {
        "poets": poets,
        "views": {
            "structure": {"scores": scores, "variance": variance, "features": FEATURES},
            "characters": character_pca(counts),
        },
    }


def render_page(data):
    """Embed analysis data without letting corpus text terminate the script tag."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", r"\u003c")
    template = files("echoes").joinpath("poet_pca.html").read_text(encoding="utf-8")
    return template.replace("<!-- PCA_DATA -->", payload)
