import unicodedata

_KEEP_PUNCTUATION = set(",.~!?'’-")


def speakable_text(text: str) -> str:
    """Keep letters and marks of any script, digits, spaces and basic punctuation; drop emoji, markdown and
    other symbols that a voice would read out or choke on."""
    return "".join(
        c for c in text
        if c in _KEEP_PUNCTUATION or unicodedata.category(c)[0] in "LMNZ" or c in "\n\t"
    )
