import argparse
import json
import sqlite3
import tomllib
from pathlib import Path

from .corpus import ingest
from .methods import render_methods
from .sampling import select
from .server import serve
from .stylometry import poet_pca, render_page


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Echoes corpus preparation")
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("ingest")
    load.add_argument("--source", required=True, type=Path)
    load.add_argument(
        "--revision",
        required=True,
        help="Full dataset Git commit SHA (recorded as supplied; checkout is not verified)",
    )
    load.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    load.add_argument("--report", type=Path, default=Path("outputs/quality.json"))
    sample = sub.add_parser("sample")
    sample.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    sample.add_argument("--config", type=Path, default=Path("configs/corpus.toml"))
    sample.add_argument("--output", type=Path, default=Path("outputs/subset.json"))
    pca = sub.add_parser("pca", help="Generate the poet PCA and data methods pages")
    pca.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    pca.add_argument("--sample", type=Path, default=Path("outputs/subset.json"))
    pca.add_argument("--output", type=Path, default=Path("outputs/poet-style.html"))
    web = sub.add_parser("serve", help="Serve the project and phrase-context search locally")
    web.add_argument("--db", type=Path, default=Path("data/poetry.sqlite"))
    web.add_argument("--sample", type=Path, default=Path("outputs/subset.json"))
    web.add_argument("--output-dir", type=Path, default=Path("outputs"))
    web.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "ingest":
        report = ingest(args.source, args.db, args.revision)
        write_json(args.report, report)
        print(json.dumps(report["counts"], ensure_ascii=False))
    elif args.command == "sample":
        config = tomllib.loads(args.config.read_text(encoding="utf-8"))
        with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as con:
            manifest = select(con, **config)
        write_json(args.output, manifest)
        print(f"Selected {len(manifest['poets'])} poets")

    elif args.command == "serve":
        try:
            serve(args.db, args.sample, args.output_dir, args.port)
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            web.error(str(exc))
    else:
        try:
            methods_output = args.output.with_name("data-cleaning.html")
            if args.output.resolve() == methods_output.resolve():
                raise ValueError("Choose a PCA filename other than data-cleaning.html")
            manifest = json.loads(args.sample.read_text(encoding="utf-8"))
            with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as con:
                page = render_page(poet_pca(con, manifest))
                methods = render_methods(con, manifest, args.output.name)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(page, encoding="utf-8")
            methods_output.write_text(methods, encoding="utf-8")
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            pca.error(str(exc))
        print(f"Wrote {args.output} and {methods_output}")


if __name__ == "__main__":
    main()
