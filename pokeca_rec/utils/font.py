import unicodedata


def full2half(c: str) -> str:
    """Converts a full-width character to a half-width character.

    Args:
        c (str): The full-width character to be converted.

    Returns:
        str: The half-width equivalent of the input character.
    """
    return unicodedata.normalize("NFKC", c)
