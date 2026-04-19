from __future__ import annotations

import unittest

from app.chat.normalizer import normalize


class NormalizeQueryTests(unittest.TestCase):
    def test_lowercase_and_collapse_space(self) -> None:
        self.assertEqual(normalize("  Altitude   HOURS  "), "altitude hours")

    def test_strip_edge_punctuation(self) -> None:
        self.assertEqual(normalize('??"When is desert storm!"'), "when is desert storm")

    def test_whens_whats_wheres(self) -> None:
        self.assertEqual(normalize("whens desert storm this year"), "when is desert storm this year")
        self.assertEqual(normalize("whats the phone for sonics"), "what is the phone for sonics")
        self.assertEqual(normalize("wheres the bowling alley"), "where is the bowling alley")

    def test_apostrophe_contractions(self) -> None:
        self.assertEqual(normalize("When's the next bmx race"), "when is the next bmx race")
        self.assertEqual(normalize("What's altitude hours"), "what is altitude hours")
        self.assertEqual(normalize("It's near Kiowa"), "it is near kiowa")

    def test_preserves_internal_hyphen_apostrophe(self) -> None:
        self.assertEqual(normalize("Rock-n-roll at O'Brien park"), "rock-n-roll at o'brien park")

    def test_empty(self) -> None:
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("   "), "")


if __name__ == "__main__":
    unittest.main()
