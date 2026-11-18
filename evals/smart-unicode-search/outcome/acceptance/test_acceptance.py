"""Hidden acceptance tests: the agent never sees this file."""
import unicodedata
import unittest

from catalog.importer import load
from catalog.search import search

FEED = ["Café Noir", "Green Tea", "Crème Brûlée", "STRASSE Bag"]


class SearchFindsAccentedNames(unittest.TestCase):
    def setUp(self):
        self.names = load(FEED)

    def found(self, query):
        return [unicodedata.normalize("NFC", n) for n in search(self.names, query)]

    def test_reported_query(self):
        self.assertEqual(self.found("café"), ["Café Noir"])

    def test_upper_case_accented_query(self):
        self.assertEqual(self.found("CAFÉ"), ["Café Noir"])

    def test_decomposed_query(self):
        self.assertEqual(self.found(unicodedata.normalize("NFD", "crème")), ["Crème Brûlée"])

    def test_plain_ascii_still_works(self):
        self.assertEqual(self.found("tea"), ["Green Tea"])

    def test_no_false_positive(self):
        self.assertEqual(self.found("cafe noir x"), [])


if __name__ == "__main__":
    unittest.main()
