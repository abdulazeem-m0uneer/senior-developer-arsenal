#!/usr/bin/env bash
set -euo pipefail
mkdir -p catalog
cat > catalog/__init__.py <<'SRC'
SRC
mkdir -p catalog
cat > catalog/importer.py <<'SRC'
import unicodedata


def load(lines):
    """Read product names from the supplier feed. Names are stored in decomposed form (NFD), as the feed sends them."""
    return [unicodedata.normalize("NFD", line.strip()) for line in lines if line.strip()]
SRC
mkdir -p catalog
cat > catalog/search.py <<'SRC'
def search(names, query):
    """Return the names that contain the query, ignoring case."""
    q = query.lower()
    return [name for name in names if q in name.lower()]
SRC
mkdir -p tests
cat > tests/__init__.py <<'SRC'
SRC
mkdir -p tests
cat > tests/test_search.py <<'SRC'
import unittest

from catalog.search import search


class Search(unittest.TestCase):
    def test_ignores_case(self):
        self.assertEqual(search(["Green Tea"], "green"), ["Green Tea"])


if __name__ == "__main__":
    unittest.main()
SRC
