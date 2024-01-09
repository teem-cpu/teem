from unittest import TestCase

from benedict import benedict as bd
from src.cpu import CPU


class AttacksTest(TestCase):
    """Test Meltdown and Spectre demo attacks."""

    def test_meltdown(self):
        """Test a simple Meltdown attack."""
        # Create CPU and load program
        cpu = CPU(bd.from_yaml("config.yml"))
        cpu.load_program_from_file("demo/meltdown.tea")

        # Execute program to the end
        while True:
            info = cpu.tick()
            if not info.executing_program:
                break

        # Check that the secret value was leaked successfully
        secret = 0x42
        leaked = cpu._exec_engine._registers[1].value // 0x10
        self.assertEqual(leaked, secret)

    def test_spectre(self):
        """Test a simple Spectre attack."""
        # Create CPU and load program
        cpu = CPU(bd.from_yaml("config.yml"))
        cpu.load_program_from_file("demo/spectre.tea")

        # Execute program to the end
        while True:
            info = cpu.tick()
            if not info.executing_program:
                break

        # Check that the secret value was leaked successfully
        secret = 0x41
        leaked = cpu._exec_engine._registers[1].value // 0x10
        self.assertEqual(leaked, secret)
