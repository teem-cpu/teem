import unittest

from src.memory import MemorySubsystem
from src.word import Word
from src.byte import Byte


class MemoryTests(unittest.TestCase):
    def test_memory(self):
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
            },
            "Mitigations":
            {
                "illegal_read_return_zero": False
            }
        }
        memory = MemorySubsystem(conf)
        import random

        # Make sure we do not pick the highest address and try to write a Word (> 1 byte) to this
        # address. Also don't pick an address from the upper half of memory.
        address = max(0, random.randint(0, 2**(Word.WIDTH - 1) - 1) - Word.WIDTH_BYTES)
        address = Word(address)

        # Reading / Writing bytes
        random_value = random.randint(0, 255)
        random_byte = Byte(random_value)
        memory.write_byte(address, random_byte)
        returned_byte = memory.read_byte(address)

        self.assertEqual(returned_byte.value.value, random_value)
        self.assertEqual(returned_byte.cycles_value, memory.cache_hit_cycles)
        self.assertEqual(returned_byte.cycles_fault, memory.num_fault_cycles)

        # Reading / Writing words
        random_value = random.randint((-1) * 2 ** (Word.WIDTH - 1), 2 ** (Word.WIDTH - 1))
        random_word = Word(random_value)
        memory.write_word(address, random_word)
        returned_word = memory.read_word(address)

        self.assertEqual(returned_word.value.signed_value, random_value)
        self.assertEqual(returned_word.cycles_value, memory.cache_hit_cycles)
        self.assertEqual(returned_word.cycles_fault, memory.num_fault_cycles)

        # Flushing the line at address (address + 1) should prevent the MEMORY from fetching all data
        # from the cache
        memory.flush_line(address + Word(1))
        self.assertEqual(memory.read_word(address + Word(1)).cycles_value, memory.cache_miss_cycles)

        # Now, (address + 1) should be cached again (because we read from it)
        self.assertIs(memory.is_addr_cached(address + Word(1)), True)

        # But if we flush it again, it shouldn't
        memory.flush_line(address + Word(1))
        self.assertIs(memory.is_addr_cached(address + Word(1)), False)

        # Accessing protected memory should induce a fault.
        mem_result = memory.read_byte(Word(2 ** (Word.WIDTH - 1)))
        self.assertIs(mem_result.fault, True)
        mem_result = memory.write_byte(Word(2 ** (Word.WIDTH - 1)), Word(1))
        self.assertEqual(mem_result.fault, True)

        # Accesing non-protected memory should be fine.
        mem_result = memory.read_byte(Word(2 ** (Word.WIDTH - 2)))
        self.assertIs(mem_result.fault, False)

        # Mitigation Test: Return 0 for illegal writes
        conf["Mitigations"]["illegal_read_return_zero"] = True
        memory = MemorySubsystem(conf)
        mem_result = memory.read_byte(Word(2 ** (Word.WIDTH - 1)))
        self.assertIs(mem_result.value.value, 0)
