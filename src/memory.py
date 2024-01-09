from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Union

from .word import Word
from .byte import Byte
from .cache import Cache, CacheFIFO, CacheLRU, CacheRR


@dataclass
class MemResult:
    """Result of a memory operation."""

    # Value returned by the memory operation
    value: Union[Word, Byte]
    # Whether the operation causes a fault
    fault: bool
    # Number of cycles we wait before returning the value
    cycles_value: int
    # Number of cycles we wait before signaling whether we fault, after we returned the value
    cycles_fault: int


class MemorySubsystem:
    """
    The memory subsystem (MS).

    In our model, the MS includes the main memory and
    cache. Contrary  to the Skylake architecture, our
    MS does not contain load- and store-buffers, and
    for the sake of simplicity, there is one cache only.
    Therefore, whether our cache is an L3 or L1 cache
    does not matter.
    """

    cache_hit_cycles: int
    cache_miss_cycles: int
    num_write_cycles: int
    num_fault_cycles: int

    memory: dict
    mem_size: int
    cache: Cache
    cache_replacement_policy: str

    _config: dict

    def __init__(self, config: dict):
        """
        A class representing the memory management unit of a CPU.
        It holds the memory itself as well as a cache.

        Parameters (optional):
            mem_size (int) -- the size of the memory (default = 2**(word size))
            cache_hit_cycles (int) -- the number of cycles it takes to read data
                from the cache (default = 2).
            cache_miss_cycles (int) -- the number of cycles it takes to read data
                from the main memory (default = 5).
            write_cycles (int) -- the number of cycles it takes to complete write
                operations (default = 5).
            cache_config(3tuple) -- the configuration of the cache. The first
                number of the number of sets, then comes the number of ways,
                and, finally, the number of entries per cache way.
                (default = (4, 4, 4))
            replacement_policy (str) -- the replacement policy to be used
                by the cache. Options are: RR (random replacement), LRU (least
                recently used), and FIFO (first-in-first-out). (default = "RR")
        """
        self._config = config

        cache_conf = config["Cache"]
        mem_conf = config["Memory"]

        self.memory = {}
        self.mem_size = 1 << Word.WIDTH

        self.cache_hit_cycles = cache_conf["cache_hit_cycles"]
        self.cache_miss_cycles = cache_conf["cache_miss_cycles"]

        self.num_write_cycles = mem_conf["num_write_cycles"]
        self.num_fault_cycles = mem_conf["num_fault_cycles"]

        self.cache_replacement_policy = cache_conf["replacement_policy"]

        cache_config = (cache_conf["sets"], cache_conf["ways"], cache_conf["line_size"])

        if self.cache_replacement_policy == "RR":
            self.cache = CacheRR(*cache_config)
        elif self.cache_replacement_policy == "LRU":
            self.cache = CacheLRU(*cache_config)
        elif self.cache_replacement_policy == "FIFO":
            self.cache = CacheFIFO(*cache_config)
        else:
            raise Exception("Unknown cache replacement policy. Check the config.yml file.")

    def _get(self, address: int) -> int:
        """
        Internal memory content retrieval. Retrieves the memory value at the given
        address, or a default value if the memory cell has not been written yet.

        Parameters:
            address (int) -- the memory address to access

        Returns:
            int: The content of the memory cell, suitable for constructing a Byte.
        """
        try:
            return self.memory[address]
        except KeyError:
            # The inaccessible half of the address space is filled with a magic value.
            if address >= self.mem_size // 2:
                return 0x42
            else:
                return 0x00

    def _get_word(self, address: int) -> int:
        """
        Internal memory content retrieval, word-sized.

        The architecture is assumed to be little-endian.

        Parameters:
            address (int) -- the memory address to access. Must be word-aligned

        Returns:
            int: The value of the word at the given address, suitable for constructing a Word.
        """
        result = 0
        for i in range(Word.WIDTH_BYTES):
            result |= self._get(address + i) << (i * Byte.WIDTH)
        return result

    def read_byte(self, address: Word, cache_side_effects: bool = True) -> MemResult:
        """
        Reads one byte from memory and returns it along with
        the number of cycles it takes to load it.

        Parameters:
            address (Word) -- the memory address from which to read
            cache_side_effects (bool) -- whether this operation should
                have side effects on the cache. True by default

        Returns:
            MemResult: Class containing the results of the memory
                operation.
        """

        data = None
        if cache_side_effects:
            data = self.cache.read(address.value)
        cycles = self.cache_hit_cycles

        if data is None:
            data = self._get(address.value)
            cycles = self.cache_miss_cycles

            if cache_side_effects or self.is_addr_cached(address):
                self._load_line(address)

        # Notice this check is done after the data was already read from
        # memory and written to the cache. Doing so and returning the data
        # to the execution even though the address should be inaccessible
        # is precisely what enables the meltdown vulnerability.
        fault = self.is_illegal_access(address)

        # Implementation of Intel's mitigation that quietly zeros out
        # the data that was illegaly read.
        # Note that 'data' is still cached. This is fine though, as the
        # attacker never gets access to 'data' at all now.
        if fault and self._config["Mitigations"]["illegal_read_return_zero"]:
            data = 0

        return MemResult(Byte(data), fault, cycles, self.num_fault_cycles)

    def write_byte(self, address: Word, data: Byte, cache_side_effects: bool = True) -> MemResult:
        """
        Writes a byte to memory.

        Parameters:
            address (Word) -- the memory address to which to write
            data (Byte) -- the Byte to write to this address
            cache_side_effects (bool) -- whether this operation should
                have side effects on the cache. True by default

        Returns:
            This function does not have a return value.
        """

        # See self.read_byte() for comments on this check.
        fault = self.is_illegal_access(address)

        if not fault:
            value = data.value
            self.memory[address.value] = value

            if cache_side_effects or self.is_addr_cached(address):
                self._load_line(address)

        return MemResult(Byte(0), fault, self.num_write_cycles, self.num_fault_cycles)

    def read_word(self, address: Word, width: int = Word.WIDTH_BYTES,
                  sign_extend: bool = False, cache_side_effects: bool = True) -> MemResult:
        """
        Reads one word from memory and returns it along with
        the number of cycles it takes to load it.
        The architecture is assumed to be little-endian.

        Parameters:
            address (Word) -- the memory address from which to read
            width (int) -- how many bytes to actually read. By default, the
                full width of a word. If less than the word width, the value
                is zero- or sign-extended
            sign_extend (bool) -- whether to sign-extend values shorter than
                a word
            cache_side_effects (bool) -- whether this operation should
                have side effects on the cache. True by default

        Returns:
            MemResult: Class containing the results of the memory
                operation.
        """

        # Read individual bytes
        bytes_read = []
        fault = False
        cycles_value = 0
        cycles_fault = 0
        for i in range(width):
            byte_res = self.read_byte(address + Word(i), cache_side_effects)
            assert isinstance(byte_res.value, Byte)

            bytes_read.append(byte_res.value)
            if byte_res.fault:
                fault = True
            cycles_value = max(cycles_value, byte_res.cycles_value)
            cycles_fault = max(cycles_fault, byte_res.cycles_fault)

        result = Word.from_some_bytes(bytes_read, sign_extend)
        return MemResult(result, fault, cycles_value, cycles_fault)

    def write_word(self, address: Word, data: Word, width: int = Word.WIDTH_BYTES,
                   cache_side_effects: bool = True) -> MemResult:
        """
        Writes a word to memory. The architecture is assumed to be little-endian.

        Parameters:
            address (Word) -- the memory address to which to write
            data (Word) -- the Word to write to this address
            width (int) -- how many low-order bytes of the word to write.
                Writes the entire word by default
            cache_side_effects (bool) -- whether this operation should
                have side effects on the cache. True by default

        Returns:
            This function does not have a return value.
        """

        # Extract the bytes to write
        # If support for big-endian architectures is ever added, this will need
        # a nontrivial case distinction.
        write_bytes = list(data.as_bytes())[:width]

        # Write individual bytes
        fault = False
        cycles_value = 0
        cycles_fault = 0
        for i, byte in enumerate(write_bytes):
            byte_res = self.write_byte(address + Word(i), byte, cache_side_effects)

            if byte_res.fault:
                fault = True
            cycles_value = max(cycles_value, byte_res.cycles_value)
            cycles_fault = max(cycles_fault, byte_res.cycles_fault)

        return MemResult(Word(0), fault, cycles_value, cycles_fault)

    def write_blob(self, address: int, data: Iterable[int]) -> None:
        """
        Write the given bytes at subsequent addresses starting at the given one.

        Used for loading program sections.

        Parameters:
            address (int) -- address where to place the first byte
            data (iterable of int) -- sequence of bytes to write

        Returns:
            This function does not have a return value.
        """
        for offset, byte in enumerate(data):
            self.write_byte(Word(address + offset), Byte(byte), cache_side_effects=False)

    def _load_line(self, address: Word, side_effects: bool = True) -> None:
        """
        Loads the entire cache line corresponding to 'addr'
        into the cache. Note that 'addr' needs to be any
        address within the cache line, it does not need
        to be the first one with offset = 0.

        Parameters:
            addr (Word) -- the address to be loaded
            side_effects (bool) -- whether the loading of
                the cache line should have an effect on
                caches taht use access times as their
                replacement policies. If false, the data
                is simply loaded into the cache, but variables
                like lru_timestamp remain unchanged.

        Returns:
            This function does not have a return value.
        """
        addr = address.value
        tag, index, offset = self.cache.parse_addr(addr)
        base_addr = addr - offset

        for i in range(self.cache.line_size):
            current_addr = base_addr + i
            self.cache.write(current_addr, self._get(current_addr), side_effects)

    def flush_line(self, address: Word) -> MemResult:
        """
        Flushes an address from the cache.

        Parameters:
            address (Word) -- the memory address to which to write

        Returns:
            This function does not have a return value.
        """
        self.cache.flush(address.value)
        return MemResult(Word(0), False, self.num_write_cycles, self.num_fault_cycles)

    def flush_all(self) -> None:
        """
        Flushes the entire cache.

        Returns:
            This function does not have a return value.
        """
        self.cache.flush_all()

    def is_addr_cached(self, address: Word) -> bool:
        """
        Returns whether the data at an address is cached.

        Parameters:
            address (Word) -- the memory address of the data

        Returns:
            bool: True if data at address is cached
        """
        return self.cache.read(address.value, side_effects=False) is not None

    def write_cycles(self) -> int:
        """
        Returns the number of cycles needed to write to memory.
        """
        return self.num_write_cycles

    def is_illegal_access(self, address: Word) -> bool:
        """
        Returns whether an acess to address is illegal.

        Parameters:
            address (Word) -- the memory address

        Returns:
            bool: True if access would raise a fault
        """
        return address.value >= self.mem_size // 2
