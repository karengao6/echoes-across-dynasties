"""Conservative normalization; no automatic simplified/traditional conversion."""

import re
import unicodedata

SPLIT = re.compile(r"[，。！？；、,.!?;\n]+")
DAMAGE = re.compile(r"[□�〓]|缺字|闕文")


def is_han(c: str) -> bool:
    n = ord(c)
    return 0x3400 <= n <= 0x4DBF or 0x4E00 <= n <= 0x9FFF or 0x20000 <= n <= 0x323AF


def han_text(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", text) if is_han(c))


def lines(paragraphs: list[str]) -> list[str]:
    return [
        clean
        for part in paragraphs
        for segment in SPLIT.split(part)
        if (clean := han_text(segment))
    ]


def observed_form(paragraphs: list[str]) -> str:
    lengths = [len(line) for line in lines(paragraphs)]
    if lengths and set(lengths) == {5}:
        return "uniform_5"
    if lengths and set(lengths) == {7}:
        return "uniform_7"
    return "mixed"
