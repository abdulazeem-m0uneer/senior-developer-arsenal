import unicodedata


def _key(text):
    return unicodedata.normalize("NFC", text).casefold()


def search(names, query):
    """Return the names that contain the query, ignoring case and Unicode normalization form."""
    q = _key(query)
    return [name for name in names if q in _key(name)]
