from __future__ import annotations

_CHAR_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


def _normalize(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index: list[int] = []
    pending_space = False
    for i, ch in enumerate(text.translate(_CHAR_MAP)):
        if ch.isspace():
            pending_space = bool(chars)
            continue
        if pending_space:
            chars.append(" ")
            index.append(i - 1)
            pending_space = False
        chars.append(ch)
        index.append(i)
    return "".join(chars), index


class SpanLocator:

    def __init__(self, text: str):
        self.text = text
        self._norm, self._index = _normalize(text)

    def locate(self, span: str) -> str | None:
        if span and span in self.text:
            return span
        needle, _ = _normalize(span)
        if not needle:
            return None
        pos = self._norm.find(needle)
        if pos < 0:
            return None
        start = self._index[pos]
        end = self._index[pos + len(needle) - 1] + 1
        return self.text[start:end]
