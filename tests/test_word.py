from unittest import TestCase

from src.word import Byte, Word, div_trunc, rem_trunc


class WordTest(TestCase):
    """Test word handling, in particular elementary arithmetic."""

    def test_types(self):
        a, b = Word(1), Word(2)
        self.assertTrue(isinstance(a.value, int))
        self.assertTrue(isinstance(a + b, Word))

    def test_reality(self):
        # There are four lights!
        self.assertEqual(Word(2) + Word(2), Word(4))

    def test_range(self):
        w = Word(0)
        self.assertEqual(w._value, 0)
        self.assertEqual(w.value, 0)
        self.assertEqual(w.signed_value, 0)

        w = Word(-42)
        self.assertEqual(w._value, 2 ** Word.WIDTH - 42)
        self.assertEqual(w.value, 2 ** Word.WIDTH - 42)
        self.assertEqual(w.signed_value, -42)

        w = Word(2 ** Word.WIDTH + 42)
        self.assertEqual(w._value, 42)
        self.assertEqual(w.value, 42)
        self.assertEqual(w.signed_value, 42)

        positive = Word(42)
        negative = Word(-42)
        self.assertTrue(positive.signed_gt(negative))
        self.assertTrue(positive.unsigned_lt(negative))

    def test_endian(self):
        # Some of the memory code depends on little-endian words.
        bs = [Byte(b) for b in (0x78, 0x56, 0x34, 0x12)]
        self.assertEqual(Word.from_bytes(bs), Word(0x12345678))

    def test_division(self):
        signed_min = -2 ** (Word.WIDTH - 1)

        # Signed division test cases (except for the corner cases) calculated
        # using a C program whose division operator, conveniently, matches
        # RISC-V semantics (or is it the other way round?).
        for a, b, q, r in (
            (1, 2, 0, 1), (1, -2,  0, 1), (-1, 2,  0, -1), (-1, -2, 0, -1),  # noqa: E241
            (2, 2, 1, 0), (2, -2, -1, 0), (-2, 2, -1,  0), (-2, -2, 1,  0),  # noqa: E241
            (3, 2, 1, 1), (3, -2, -1, 1), (-3, 2, -1, -1), (-3, -2, 1, -1),  # noqa: E241
            (4, 2, 2, 0), (4, -2, -2, 0), (-4, 2, -2,  0), (-4, -2, 2,  0),  # noqa: E241
            (1, 0, -1, 1), (0, 0, -1, 0), (-1, 0, -1, -1),
            (signed_min, -1, signed_min, 0), (signed_min, signed_min, 1, 0)
        ):
            self.assertEqual(Word(div_trunc(a, b)).signed_value, q)
            self.assertEqual(Word(rem_trunc(a, b)).signed_value, r)

        # For unsigned division, the semantics of Python and RISC-V match.
        for a, b in (
            (0, 1), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (2, 2), (3, 3),
            (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1),
            (signed_min, 1), (signed_min, -1), (signed_min, signed_min)
        ):
            aa, ab = Word(a).value, Word(b).value
            self.assertEqual(div_trunc(aa, ab), aa // ab)
            self.assertEqual(rem_trunc(aa, ab), aa % ab)
