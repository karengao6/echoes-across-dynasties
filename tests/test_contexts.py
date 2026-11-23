import re
import sqlite3
from contextlib import closing
from json import dumps

from echoes.contexts import phrase_graph, poem_contexts, terms


def test_literal_matches_are_counted_and_repeated_passages_deduplicated():
    assert poem_contexts(["秋，風。秋（風。"], re.compile("秋風")) == (0, [])
    assert poem_contexts(["哈哈哈"], re.compile("哈哈")) == (1, [("哈哈哈",)])
    assert poem_contexts(["秋風，明月，明月，秋風，明月"], re.compile("秋風")) == (
        2, [("秋風", "明月"), ("明月", "秋風", "明月")]
    )
    assert poem_contexts(["明，秋風，月，明，秋風，月"], re.compile("秋風")) == (
        2, [("明", "秋風", "月")]
    )
    assert terms(("明秋風月",), re.compile("秋風")) == {"明": 1, "月": 1}


def test_scope_and_matching_poems_control_graph_eligibility():
    with closing(sqlite3.connect(":memory:")) as con:
        con.execute("""CREATE TABLE poems (
            id TEXT, poet_id TEXT, title TEXT, n_chars INTEGER, text TEXT, paragraphs TEXT
        )""")
        poets = []
        for poet_id, count in (("a", 5), ("b", 5), ("c", 4)):
            ids = [f"{poet_id}{i}" for i in range(count)]
            poets.append({
                "poet_id": poet_id, "author": poet_id, "dynasty": "tang", "poem_ids": ids[:3],
            })
            con.executemany(
                "INSERT INTO poems VALUES (?, ?, ?, ?, ?, ?)",
                [(id_, poet_id, "詩", 6, "秋風秋風明月", dumps(["秋風秋風，明月。"])) for id_ in ids],
            )
        all_poems = phrase_graph(con, {"poets": poets}, "秋風", "all")
        simplified = phrase_graph(con, {"poets": poets}, "秋风", "all")
        exact = phrase_graph(con, {"poets": poets}, "秋风", "all", "exact")
        sample = phrase_graph(con, {"poets": poets}, "秋風", "sample")

    assert simplified["spellings"] == ["秋風", "秋风"]
    assert simplified["edges"] == all_poems["edges"]
    assert simplified["poets"] == all_poems["poets"]
    assert exact["nodes"] == []
    assert all_poems["pairCount"] == 1
    assert all_poems["medianScore"] == all_poems["maxScore"]
    assert all_poems["nodes"] == ["a", "b"]
    assert len(all_poems["edges"]) == 1
    assert abs(all_poems["edges"][0]["score"] - 1) < 1e-10
    assert all_poems["poets"][2]["occurrences"] == 8
    assert all_poems["poets"][2]["passages"]
    assert sample["nodes"] == []
    assert [poet["matching"] for poet in sample["poets"]] == [3, 3, 3]
