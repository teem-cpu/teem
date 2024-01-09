from src.ui import *
from src.word import Word
from src.memory import MemorySubsystem
from src.frontend import Frontend
from src.bpu import BPU, BTB, RSB
from src.execution import ExecutionEngine
from benedict import benedict as bd


# # print current PC position
# print_header("Program", BOLD + RED + ENDC)
# print("  " + FAINT + "37 " + ENDC + CYAN + "ADD " + ENDC + YELLOW + "R0, R0" + ENDC)
# print(GREEN + "► " + ENDC + FAINT + "38 " + ENDC + CYAN + "MOV " + ENDC + YELLOW + "R1, R7" + ENDC)
# print("  " + FAINT + "39 " + ENDC + CYAN + "LD  " + ENDC + YELLOW + "R1, R0" + ENDC)
# print("  " + FAINT + "40 " + ENDC + CYAN + "DIV " + ENDC + YELLOW + "R0, R0" + ENDC)

# # print reservation stations
# print_header("ReservationStations", BOLD + GREEN + ENDC)
# from tabulate import tabulate
# print()
# print(tabulate([["ADD", "R0", "R0"], ["FLUSH", "-","-"]], headers=['Instruction', 'OP1', 'OP2'], tablefmt='orgtbl'))
# print()

# # print memory
# print_header("Memory", BOLD + YELLOW + ENDC)
# print()
# from random import randrange
# rand_arr = [randrange(0, 0xFFFF) for _ in range(0xFFFF)]
# print_memory(rand_arr, lines=8, base=0x0000)
# print()

# # print registers
# print_header("Registers", BOLD + CYAN + ENDC)
# print(BOLD+GREEN + "R0:" + ENDC + " " + FAINT + "0x" + ENDC + "EB83")
# print(BOLD+GREEN + "R1:" + ENDC + " " + FAINT + "0x" + ENDC + "031C")
# print(BOLD+GREEN + "R2:" + ENDC + " " + FAINT + "0x" + ENDC + "0000")
# print(BOLD+GREEN + "R3:" + ENDC + " " + FAINT + "0x" + ENDC + "DEAD")

from unittest import TestCase


class UITest(TestCase):
    """Test the UI."""

    def test_memory(self):
        print()
        conf = {
            "Cache":
            {
                "cache_hit_cycles": 2,
                "cache_miss_cycles": 5,
                "line_size": 4,
                "ways": 4,
                "sets": 4,
                "replacement_policy": "LRU"
            },
            "Memory":
            {
                "layout":
                [
                    {
                        "access": True,
                        "end": 32767,
                        "start": 0
                    },
                    {
                        "access": True,
                        "end": 65535,
                        "start": 32768
                    }
                ],
                "num_fault_cycles": 8,
                "num_write_cycles": 5
            }
        }
        memory = MemorySubsystem(conf)
        from random import randrange
        for _ in range(5000):
            memory.write_byte(
                Word(
                    randrange(
                        0, memory.mem_size)), Word(
                    randrange(
                        0, 0xFF)))
        header_memory(memory)

    def test_registers(self):
        print()
        config = bd.from_yaml('config.yml')
        memory = MemorySubsystem(config)
        bpu = BPU(config)
        btb = BTB(config)
        rsb = RSB(config)
        frontend = Frontend(bpu, btb, rsb, [], 0, config)
        engine = ExecutionEngine(frontend, memory, bpu, btb, config)
        header_regs(engine)

    def test_cache(self):
        print()
        memory = MemorySubsystem(bd.from_yaml('config.yml'))
        from random import randrange
        for _ in range(50000):
            memory.write_byte(
                Word(
                    randrange(
                        0, memory.mem_size)), Word(
                    randrange(
                        0, 0xFF)))
        print_header("Cache", ENDC)
        print()
        print_cache(memory, False, False)
        print()

    def test_end(self):
        print()
        print_header("END")

    def test_box(self):
        print()
        print_header("Box", BOLD + RED + ENDC)
        print(BLUE + BOX_SOUTHEAST + BOX_HORIZOZTAL + BOX_SOUTHWEST + "\n" + BOX_VERTICAL + " " + BOX_VERTICAL + "\n" + BOX_NORTHEAST + BOX_HORIZOZTAL + BOX_NORTHWEST + ENDC)

# test = UITest()
# test.test_memory()
# test.test_registers()
# test.test_cache()
# test.test_end()
