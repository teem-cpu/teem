from unittest import TestCase

from collections import Counter

from src.instructions import Instruction, all_instructions
from src.parser import REGISTER_NAMES, Parser


class ParserTest(TestCase):
    """Test the parser."""

    def test_register_names(self):
        """Ensure the register name mapping is valid."""
        # Every register from x0 to x31 has at least one alternative name.
        self.assertEqual(set(REGISTER_NAMES.values()), set(f'x{i}' for i in range(32)))

        # Every register but x8 (a.k.a. fp a.k.a. s0) has exactly one alternative name.
        regname_counts = Counter(REGISTER_NAMES.values())
        self.assertEqual(regname_counts.pop('x8'), 2)
        self.assertTrue(all(v == 1 for v in regname_counts.values()))

        # The alternative names have few "stems".
        self.assertEqual(set(n.rstrip('0123456789') for n in REGISTER_NAMES.keys()),
                         {'zero', 'ra', 'sp', 'gp', 'tp', 'fp', 't', 's', 'a'})

        # No registers from numbered series may be skipped.
        for series, size in ('t', 7), ('s', 12), ('a', 8):
            self.assertGreaterEqual(set(REGISTER_NAMES.keys()),
                                    set(f'{series}{i}' for i in range(size)))

    def test_operand_indices(self):
        """Ensure all standard instruction types have sane operand mappings."""
        for ity in all_instructions.values():
            self.assertIn(ity.destination(), (None, 0))

            source_count = len(ity.sources())
            if ity.destination() is not None:
                expected_sources = list(range(1, source_count + 1))
            else:
                expected_sources = list(range(source_count))
            self.assertEqual(ity.sources(), expected_sources)

    def test_program(self):
        """Test parsing of a simple program."""
        addi = all_instructions["addi"]
        beq = all_instructions["beq"]

        p = Parser.from_default()
        prog = p.parse(
            """
            a: addi r1, r0, 100
            beq r0, r0, a
            """
        )

        self.assertEqual(prog.entry_point, 0x80)
        self.assertEqual(prog.text_segment.code, [
            Instruction(0x80, addi, [1, 0, 100]),
            Instruction(0x84, beq, [0, 0, 0x80]),
        ])
        self.assertEqual(prog.data_segment.data, b'\0\0\0\0')
        self.assertEqual(prog.symbols, {'a': 0x80})

    def test_exceptions(self):
        """Test that the correct exceptions are raised on invalid instructions."""
        addi = all_instructions["addi"]
        beq = all_instructions["beq"]

        p = Parser.from_default()
        p.add_instruction(addi)
        p.add_instruction(beq)

        with self.assertRaises(ValueError) as exc:
            p.parse("invalid r0, 0")
        self.assertIn("Unknown instruction type", str(exc.exception))

        with self.assertRaises(ValueError) as exc:
            p.parse("addi r0, 0")
        self.assertIn("does not take 2 operands", str(exc.exception))
