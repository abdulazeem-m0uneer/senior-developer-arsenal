#!/usr/bin/env bash
set -euo pipefail
mkdir -p tests
cat > paging.py <<'PY'
def page(items, number, size):
    """Return page `number` (1-based) of `items`, `size` items per page."""
    start = number * size
    return items[start:start + size]
PY
cat > tests/test_paging.py <<'PY'
from paging import page

ITEMS = list(range(25))


def test_first_page():
    assert page(ITEMS, 1, 10) == list(range(0, 10))


def test_second_page():
    assert page(ITEMS, 2, 10) == list(range(10, 20))


def test_last_page_is_short():
    assert page(ITEMS, 3, 10) == [20, 21, 22, 23, 24]
PY
cat > ci.log <<'LOG'
FAILED tests/test_paging.py::test_first_page - assert [10, 11, ..., 19] == [0, 1, ..., 9]
FAILED tests/test_paging.py::test_second_page - assert [20, 21, 22, 23, 24] == [10, 11, ..., 19]
FAILED tests/test_paging.py::test_last_page_is_short - assert [] == [20, 21, 22, 23, 24]
3 failed in 0.04s
LOG
