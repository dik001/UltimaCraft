from __future__ import annotations

import unicodedata


def normalized_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()

