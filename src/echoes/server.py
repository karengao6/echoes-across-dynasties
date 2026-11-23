"""Serve the project locally with a read-only corpus connection per search."""

import json
import sqlite3
from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from re import DOTALL, sub
from urllib.parse import parse_qs, urlsplit

from .contexts import phrase_graph


PAGE_LABELS = {
    "/poet-style.html": "Poet style",
    "/phrase-contexts.html": "Phrase contexts",
    "/data-cleaning.html": "Data and methods",
}


def app_page(document, current_path):
    links = []
    for path, label in PAGE_LABELS.items():
        current = ' aria-current="page"' if path == current_path else ""
        links.append(f'<a href="{path}"{current}>{escape(label)}</a>')
    header = (
        '<header class="app-header"><div class="app-bar">'
        '<a class="app-brand" href="/">Echoes Across Dynasties</a>'
        f'<nav aria-label="Project pages">{"".join(links)}</nav>'
        '</div></header>'
    )
    # The standalone reports include their own companion links.
    document = sub(
        r'<nav aria-label="Project pages">.*?</nav>\s*', "", document, count=1, flags=DOTALL
    )
    document = document.replace("</style>", '</style>\n<link rel="stylesheet" href="/app.css">', 1)
    return document.replace("<main>", f"{header}\n<main>", 1)


def serve(db, sample, output, port):
    database = db.resolve().as_uri() + "?mode=ro"
    manifest = json.loads(sample.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(database, uri=True)) as con:
        row = con.execute("SELECT value FROM metadata WHERE key='ingestion'").fetchone()
        metadata = json.loads(row[0]) if row else {}
        if any(metadata.get(key) != manifest[key] for key in ("dataset_revision", "sources")):
            raise ValueError("Sample manifest and corpus database have different source provenance")
    documents = {
        "/" + name: (output / name).read_text(encoding="utf-8")
        for name in ("poet-style.html", "data-cleaning.html")
    }
    resources = files("echoes")
    documents["/phrase-contexts.html"] = resources.joinpath(
        "phrase_contexts.html"
    ).read_text(encoding="utf-8")
    pages = {path: app_page(document, path) for path, document in documents.items()}
    pages["/"] = pages["/poet-style.html"]
    stylesheet = resources.joinpath("app.css").read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content_type, body):
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path in pages:
                self.reply(200, "text/html", pages[url.path])
            elif url.path == "/app.css":
                self.reply(200, "text/css", stylesheet)
            elif url.path == "/api/phrase":
                query = parse_qs(url.query)
                try:
                    with closing(sqlite3.connect(database, uri=True)) as con:
                        result = phrase_graph(
                            con, manifest, query.get("q", [""])[0],
                            query.get("scope", ["all"])[0], query.get("script", ["both"])[0],
                        )
                except ValueError as exc:
                    self.reply(400, "application/json", json.dumps({"error": str(exc)}))
                except sqlite3.Error as exc:
                    self.log_error("%s", exc)
                    self.reply(500, "application/json", '{"error":"Could not read the corpus."}')
                else:
                    self.reply(200, "application/json", json.dumps(result, ensure_ascii=False))
            else:
                self.send_error(404)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Open http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
