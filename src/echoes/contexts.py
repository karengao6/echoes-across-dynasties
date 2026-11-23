"""Literal verse search and phrase-specific character TF-IDF."""

import json
import math
import unicodedata
from collections import Counter

from .text import SPLIT, han_text, is_han

MIN_POEMS = 5


def unit(vector):
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {term: value / norm for term, value in vector.items()} if norm else {}


def poem_contexts(paragraphs, phrase):
    verse = [
        segment.strip()
        for paragraph in paragraphs
        for segment in SPLIT.split(paragraph)
        if han_text(segment)
    ]
    contexts = {}
    occurrences = 0
    for index, line in enumerate(verse):
        normalized = unicodedata.normalize("NFC", line)
        count = normalized.count(phrase)
        if count:
            occurrences += count
            start, end = max(0, index - 1), min(len(verse), index + 2)
            passage = tuple(verse[start:end])
            contexts[passage] = None
    return occurrences, list(contexts)


def terms(passage, phrase):
    counts = Counter()
    for line in passage:
        masked = unicodedata.normalize("NFC", line).replace(phrase, " ")
        # Break at the target and at any other non-Han text.
        for run in "".join(char if is_han(char) else " " for char in masked).split():
            for size in (1, 2, 3):
                counts.update(run[i:i + size] for i in range(len(run) - size + 1))
    return counts


def phrase_graph(con, manifest, phrase, scope):
    phrase = unicodedata.normalize("NFC", phrase.strip())
    if not 1 <= len(phrase) <= 64 or not all(map(is_han, phrase)):
        raise ValueError("Enter 1–64 Han characters using the corpus spelling, such as 秋風.")
    if scope not in {"all", "sample"}:
        raise ValueError("Choose all cleaned poems or sampled poems.")

    poets, documents, frequency = [], {}, Counter()
    context_count = 0
    for poet in manifest["poets"]:
        poet_id = poet["poet_id"]
        sampled = set(poet["poem_ids"])
        poems = occurrences = characters = matching = 0
        passages, matched_documents = [], []
        rows = con.execute(
            """SELECT id, title, n_chars, instr(text, ?),
                      CASE WHEN instr(text, ?) > 0 THEN paragraphs END
               FROM poems WHERE poet_id = ? ORDER BY id""",
            (phrase, phrase, poet_id),
        )
        for poem_id, title, length, candidate, paragraphs in rows:
            if scope == "sample" and poem_id not in sampled:
                continue
            poems += 1
            characters += length
            if not candidate:
                continue
            count, contexts = poem_contexts(json.loads(paragraphs), phrase)
            if not count:
                continue
            occurrences += count
            matching += 1
            if len(passages) < 5:
                passages.append({"title": title, "lines": contexts[0]})
            matched_documents.append([terms(passage, phrase) for passage in contexts])
        poets.append({
            "id": poet_id, "author": poet["author"], "dynasty": poet["dynasty"],
            "poems": poems, "characters": characters, "occurrences": occurrences,
            "matching": matching, "passages": passages,
        })
        if matching >= MIN_POEMS:
            documents[poet_id] = matched_documents
            for poem in matched_documents:
                for context in poem:
                    frequency.update(context.keys())
                    context_count += 1

    idf = {term: 1 + math.log((1 + context_count) / (1 + n)) for term, n in frequency.items()}
    vectors = {}
    for poet_id, poems in documents.items():
        pooled = Counter()
        for poem in poems:
            for context in poem:
                weighted = unit({term: count * idf[term] for term, count in context.items()})
                for term, value in weighted.items():
                    pooled[term] += value / len(poem)
        vector = unit(pooled)
        if vector:
            vectors[poet_id] = vector

    neighbors = {poet_id: [] for poet_id in vectors}
    ids = list(vectors)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            a, b = sorted((vectors[left], vectors[right]), key=len)
            score = min(1, sum(value * b.get(term, 0) for term, value in a.items()))
            if score > 0:
                neighbors[left].append((score, right))
                neighbors[right].append((score, left))
    edges = {}
    for left, matches in neighbors.items():
        for score, right in sorted(matches, key=lambda match: (-match[0], match[1]))[:3]:
            edges[tuple(sorted((left, right)))] = score
    return {
        "phrase": phrase,
        "poets": poets,
        "nodes": ids,
        "edges": [
            {"left": left, "right": right, "score": score}
            for (left, right), score in sorted(edges.items(), key=lambda item: -item[1])
        ],
    }
