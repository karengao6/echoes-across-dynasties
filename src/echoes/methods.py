"""Render the cleaning and sampling audit from the same database as the plot."""

import json
from collections import Counter
from html import escape
from importlib.resources import files
from urllib.parse import quote

from .stylometry import FEATURES

CLEANING_COUNTS = (
    ("input_records", "Records read"),
    ("invalid_record", "Non-object records excluded"),
    ("invalid_schema", "Records with missing or invalid fields excluded"),
    ("anonymous_author", "Anonymous attributions excluded"),
    ("damage_marker", "Records with known damage markers excluded"),
    ("no_han_text", "Records without Han text excluded"),
    ("duplicate_records", "Redundant copies collapsed"),
    ("conflicting_attribution_records", "Records with conflicting attributions excluded"),
    ("retained_poems", "Distinct poems retained"),
)

FEATURE_REASONS = (
    "Measures how much of the sample uses five-character lines, a common line length in shi.",
    "Measures how much uses seven-character lines. The remainder uses other lengths.",
    "Measures typical line length across the sample, including lines of other lengths.",
    "Shows whether line lengths are consistent or varied, even when two poets have the same mean.",
    "Captures typical poem size in lines, which can reflect the mix of forms in the sample.",
    "Captures reuse of characters within a poem, including repeated words and motifs.",
    "Captures whole-line reuse within a poem, including refrains and parallel repetitions.",
)


def render_methods(con, manifest, plot_name):
    """Count eligible poet identities under the active form filter at several cutoffs."""
    report = json.loads(
        con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()[0]
    )
    form = manifest["form"]
    poem_counts = con.execute(
        """
        SELECT dynasty, COUNT(*) FROM poems
        WHERE (? = '' OR form = ?)
        GROUP BY dynasty, poet_id
        """,
        (form, form),
    ).fetchall()

    cutoff = manifest["poems_per_poet"]
    eligibility = []
    for minimum in sorted({25, 50, 100, 200, cutoff}):
        counts = Counter(dynasty for dynasty, size in poem_counts if size >= minimum)
        label = f"{minimum:,}" + (" (used in plot)" if minimum == cutoff else "")
        eligibility.append(
            f'<tr><th scope="row">{label}</th><td>{counts["tang"]:,}</td>'
            f'<td>{counts["song"]:,}</td><td>{sum(counts.values()):,}</td></tr>'
        )

    sample = Counter(poet["dynasty"] for poet in manifest["poets"])
    counts = report["counts"]
    scheme = (
        "This build reads the main Tang and Song shi JSON files directly inside the source "
        "directory. For an upstream checkout, that directory is 全唐诗. The error and "
        "strains subdirectories are outside the import."
        if report.get("source_selection") == "main_shards" else
        "This database predates the main-directory restriction. Its ingestion may have "
        "included matching files in auxiliary directories."
    )
    template = files("echoes").joinpath("data_cleaning.html").read_text(encoding="utf-8")
    return template.format(
        plot_href=quote(plot_name, safe=""),
        source_selection=scheme,
        revision=escape(report["dataset_revision"]),
        file_count=f'{len(report["sources"]):,}',
        cleaning_rows="".join(
            f'<tr><th scope="row">{label}</th><td>{counts.get(key, 0):,}</td></tr>'
            for key, label in CLEANING_COUNTS
        ),
        eligibility_rows="".join(eligibility),
        feature_rows="".join(
            f"<dt>{feature.capitalize()}</dt><dd>{reason}</dd>"
            for feature, reason in zip(FEATURES, FEATURE_REASONS, strict=True)
        ),
        form=escape(form or "all observed line forms"),
        seed=manifest["seed"],
        cutoff=f"{cutoff:,}",
        tang=sample["tang"],
        song=sample["song"],
        sampled_poems=f'{sum(len(p["poem_ids"]) for p in manifest["poets"]):,}',
    )
