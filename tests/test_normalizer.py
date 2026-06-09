from __future__ import annotations

import unittest

from app.chat.normalizer import normalize, spell_correct


class NormalizeQueryTests(unittest.TestCase):
    def test_lowercase_and_collapse_space(self) -> None:
        self.assertEqual(normalize("  Altitude   HOURS  "), "altitude hours")

    def test_strip_edge_punctuation(self) -> None:
        self.assertEqual(normalize('??"When is desert storm!"'), "when is desert storm")

    def test_whens_whats_wheres(self) -> None:
        self.assertEqual(
            normalize("whens desert storm this year"), "when is desert storm this year"
        )
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


class SpellCorrectTests(unittest.TestCase):
    """Adversarial set for the shared domain spell-correct layer.

    MUST correct misspelled categories/trades; MUST NOT cross-correct between
    distinct real words or mangle distinctive proper nouns (business names).
    """

    # --- MUST route/correct -------------------------------------------------

    def test_corrects_misspelled_trades(self) -> None:
        cases = {
            "plummbers": "plumbers",
            "electritian": "electrician",
            "resturant": "restaurant",
            "dentis": "dentist",
            "mecanic": "mechanic",  # mechanic → auto-repair downstream
        }
        for typo, expected in cases.items():
            self.assertEqual(spell_correct(typo), expected, typo)

    def test_corrects_within_a_phrase(self) -> None:
        # "dawg" is slang (alias); "groomer" is already canonical.
        self.assertEqual(spell_correct("dawg groomer"), "dog groomer")
        # Correction survives the full normalize() funnel with locality/filler.
        self.assertEqual(normalize("Best PLUMMBERS in Lake Havasu"), "best plumbers in lake havasu")
        self.assertEqual(normalize("wheres the dentis"), "where is the dentist")

    def test_curated_trade_aliases(self) -> None:
        for typo, expected in {
            "plumer": "plumber",
            "salaon": "salon",
            "gymn": "gym",
            "coffe": "coffee",
            "carpentar": "carpenter",
            "vetrinarian": "veterinarian",
        }.items():
            self.assertEqual(spell_correct(typo), expected, typo)

    # --- MUST NOT cross-correct --------------------------------------------

    def test_does_not_cross_correct_distinct_real_words(self) -> None:
        # Each of these is a real word that sits within edit distance of a
        # category term but means something else — must pass through untouched.
        for word in ("bars", "cars", "vets", "jets", "hotels", "hostels",
                     "pools", "tools", "saloon", "sparks", "snails", "moves"):
            self.assertEqual(spell_correct(word), word, word)

    def test_does_not_mangle_proper_nouns(self) -> None:
        # Distinctive business / place names must never be "corrected".
        for name in ("mudshark", "javelina", "barts", "kiowa", "altitude"):
            self.assertEqual(spell_correct(name), name, name)

    # --- properties ---------------------------------------------------------

    def test_idempotent(self) -> None:
        for q in ("plummbers", "dawg groomer", "best resturant", "mudshark brewry"):
            once = spell_correct(q)
            self.assertEqual(spell_correct(once), once, q)

    def test_empty_and_whitespace(self) -> None:
        self.assertEqual(spell_correct(""), "")
        self.assertEqual(spell_correct("   "), "   ")

    def test_in_vocab_terms_unchanged(self) -> None:
        for term in ("plumbers", "restaurants", "dentists", "barber", "coffee"):
            self.assertEqual(spell_correct(term), term, term)


if __name__ == "__main__":
    unittest.main()
