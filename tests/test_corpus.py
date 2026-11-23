import json
import sqlite3

import pytest

from echoes.corpus import ingest
from echoes.sampling import select
from echoes.text import han_text, lines, observed_form

SHA = "a" * 40


def poem(author, text):
    return {"author": author, "title": "題", "paragraphs": [text]}


def shard(tmp_path, dynasty, records):
    root = tmp_path / "raw"
    root.mkdir(exist_ok=True)
    (root / f"poet.{dynasty}.0.json").write_text(json.dumps(records))
    return root


def test_normalization():
    assert han_text("明月，松間照。") == "明月松間照"
    assert lines(["明月松間照，清泉石上流。"]) == ["明月松間照", "清泉石上流"]
    assert observed_form(["明月松間照，清泉石上流。"]) == "uniform_5"
    assert observed_form(["明月，清泉石上流。"]) == "mixed"


def test_dedup_conflicts_damage_and_provenance(tmp_path):
    root = shard(
        tmp_path,
        "tang",
        [
            poem("甲", "明月。"),
            poem("甲", "明月！"),
            poem("乙", "流水。"),
            poem("丙", "流水。"),
            poem("甲", "山□水"),
            {"author": "甲"},
            poem("佚名", "秋風。"),
        ],
    )
    db = tmp_path / "poems.sqlite"
    report = ingest(root, db, SHA)
    assert report["counts"]["retained_poems"] == 1
    assert report["counts"]["duplicate_records"] == 1
    assert report["counts"]["conflicting_attribution_records"] == 2
    assert report["counts"]["damage_marker"] == 1
    with sqlite3.connect(db) as con:
        paragraphs, provenance = con.execute("SELECT paragraphs, provenance FROM poems").fetchone()
    assert json.loads(paragraphs) == ["明月。"]
    assert len(json.loads(provenance)) == 2
    with pytest.raises(FileExistsError):
        ingest(root, db, SHA)


def test_sampling_and_shortage(tmp_path):
    root = shard(tmp_path, "tang", [poem("甲", "明月"), poem("甲", "清泉"), poem("乙", "山河")])
    shard(tmp_path, "song", [poem("丙", "春風"), poem("丙", "秋雨"), poem("丁", "天地")])
    db = tmp_path / "poems.sqlite"
    ingest(root, db, SHA)
    with sqlite3.connect(db) as con:
        a = select(con, poets_per_dynasty=1, poems_per_poet=2)
        assert a == select(con, poets_per_dynasty=1, poems_per_poet=2)
        assert len(a["poets"]) == 2
        assert all(len(p["poem_ids"]) == 2 for p in a["poets"])
        with pytest.raises(ValueError, match="eligible"):
            select(con, poets_per_dynasty=2, poems_per_poet=2)
        with pytest.raises(ValueError):
            select(con, poets_per_dynasty=0)


def test_bad_shard_does_not_create_database(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    (root / "poet.tang.0.json").write_text("{}")
    db = tmp_path / "poems.sqlite"
    with pytest.raises(ValueError, match="array"):
        ingest(root, db, SHA)
    assert not db.exists()


def test_file_scope_hashes_and_original_provenance(tmp_path):
    import hashlib

    root = shard(tmp_path, "tang", [poem("甲", "明月。"), poem("甲", "明月！")])
    nested = root / "nested"
    nested.mkdir()
    # Matching shard names in nested directories are outside the import.
    (nested / "poet.song.1000.json").write_text("not JSON")
    shard(tmp_path, "song", [poem("乙", "流水。")])
    # Unrelated collections must never be parsed, even if their JSON is invalid.
    (root / "ci.song.0.json").write_text("not JSON")
    (root / "authors.tang.json").write_text("not JSON")
    db = tmp_path / "poems.sqlite"
    report = ingest(root, db, SHA)
    assert report["counts"]["input_records"] == 3
    assert report["counts"]["retained_poems"] == 2
    assert report["dataset_revision"] == SHA
    for source in report["sources"]:
        assert source["sha256"] == hashlib.sha256((root / source["path"]).read_bytes()).hexdigest()
    with sqlite3.connect(db) as con:
        provenance = json.loads(
            con.execute("SELECT provenance FROM poems WHERE author = ?", ("甲",)).fetchone()[0]
        )
        stored_report = json.loads(con.execute("SELECT value FROM metadata").fetchone()[0])
    assert stored_report == report
    assert [r["paragraphs"] for r in provenance] == [["明月。"], ["明月！"]]
    assert [r["source_index"] for r in provenance] == [0, 1]
    assert all("provenance" not in r and "id" not in r for r in provenance)


@pytest.mark.parametrize("revision", ["main", "a" * 39, "g" * 40])
def test_invalid_revision_does_not_create_database(tmp_path, revision):
    root = shard(tmp_path, "tang", [poem("甲", "明月")])
    db = tmp_path / "poems.sqlite"
    with pytest.raises(ValueError, match="commit SHA"):
        ingest(root, db, revision)
    assert not db.exists()


def test_missing_source_does_not_create_database(tmp_path):
    db = tmp_path / "poems.sqlite"
    with pytest.raises(ValueError, match="directory"):
        ingest(tmp_path / "missing", db, SHA)
    assert not db.exists()


def test_checkout_ingests_only_main_collection_shards(tmp_path):
    root = tmp_path / "checkout"
    main = root / "全唐诗"
    main.mkdir(parents=True)
    (main / "poet.tang.0.json").write_text(json.dumps([poem("甲", "明月。")]))
    for directory in (root, main / "error", root / "strains" / "json"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "poet.tang.0.json").write_text("not JSON")

    report = ingest(root, tmp_path / "poems.sqlite", SHA)

    assert report["counts"]["retained_poems"] == 1
    assert [source["path"] for source in report["sources"]] == ["全唐诗/poet.tang.0.json"]
