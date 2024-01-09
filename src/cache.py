from __future__ import annotations

import random
from time import time
from typing import Generic, Optional, Type, TypeVar

from .word import Word


class CacheLine:
    """
    A helper class representing a cache line in a cache.

    It may be used if no additional data is needed to
    implement the cache replacement policy. An example of
    this is the random replacement policy.

    If additional information, such as the last time of
    access, is needed by the replacement policy, this
    class should be extended accordingly.
    """
    data: list[Optional[int]]
    tag: Optional[int]
    line_size: int

    def __init__(self, line_size: int):
        self.data = [None] * line_size
        self.tag = None
        self.line_size = line_size

    def is_in_use(self):
        """
        Returns true if the current cache line is
        in use by checking if the tag is set.
        """
        return self.tag is not None

    def check_tag(self, tag: int) -> bool:
        """
        Returns if the given tag matches this cache
        line's tag.

        Parameters:
            tag (int) -- the tag to compare

        Returns:
            bool: True if the cache line's tag matches
        """
        return self.is_in_use() and self.tag == tag

    def set_tag(self, tag: int) -> None:
        """
        Sets the cache line's tag.

        Parameters:
            tag (int) -- the new tag

        Returns:
            This function does not have a return value.
        """
        self.tag = tag

    def read(self, offset: int, side_effects: bool = True) -> Optional[int]:
        """
        Reads from the cache line at index 'offset'.
        Note that this function does NOT check for
        any tags.

        Parameters:
            offset (int) -- the offset at which to read
            side_effects (bool) -- whether the read should
                have an effect on caches that use access
                times for their replacement policy, like LRU.

        Returns:
            int: The data saved at 'offset'.
            Returns 'None' if no data is present.
        """
        return self.data[offset]

    def write(self, offset: int, data: int, side_effects: bool = True) -> None:
        """
        Writes data to the cache line at index 'offset'.

        Parameters:
            offset (int) -- the offset to which to write
            data (int)   -- the data to write
            side_effects (bool) -- whether the write should
                have an effect on the caches that use access
                times for their replacement policy, like LRU.
                Note that the default CacheLine does not use
                this parameter.

        Returns:
            This function does not have a return value.
        """
        self.data[offset] = data

    def flush(self) -> None:
        """
        Flushes the data held by this cache line
        and clears its tag.
        """
        self.data[:] = [None] * self.line_size
        self.tag = None


LT = TypeVar('LT', bound=CacheLine)


class Cache(Generic[LT]):
    """
    An abstract class implementing a cache. Using this class directly is not possible, as it
    does not implement any cache replacement policies.

    Instead, use any of the following classes: CacheRR, CacheLRU, CacheFIFO
    """

    num_sets: int
    num_lines: int
    line_size: int
    sets: list[list[LT]]

    def __init__(self, num_sets: int, num_lines: int, line_size: int, line_class: Type[LT]):
        self.sets = [[line_class(line_size) for a in range(num_lines)]
                     for b in range(num_sets)]

        if num_sets <= 0 or num_lines <= 0 or line_size <= 0:
            raise Exception("Invalid cache parameters.")
        elif line_size % Word.WIDTH_BYTES != 0:
            raise Exception("Cache line size must be a multiple of the word size")

        self.num_sets = num_sets
        self.num_lines = num_lines
        self.line_size = line_size

        self.num_offset_bits = self.line_size.bit_length() - 1
        self.num_index_bits = self.num_sets.bit_length() - 1
        self.num_tag_bits = Word.WIDTH - self.num_offset_bits - self.num_index_bits

        if self.num_tag_bits <= 0:
            raise Exception("Not enough bits left for cache tag")

    def parse_addr(self, addr: int) -> tuple[int, int, int]:
        """
        Parses the given address and returns a 3-tuple consisting of
        tag, index, and offset to access the cache.

        Parameters:
            addr (int) -- the address to parse

        Returns:
            tuple[int, int, int]: tag, index, offset
        """

        tag = addr >> (self.num_offset_bits + self.num_index_bits)
        index = (addr >> self.num_offset_bits) & ((1 << self.num_index_bits) - 1)
        offset = addr & ((1 << self.num_offset_bits) - 1)

        return tag, index, offset

    def _apply_replacement_policy(self, addr: int, data: int) -> None:
        """
        Applies the corresponding replacement policy by choosing a cache line that
        is to be replaced.
        When called, all cache lines of a cache set must be already in use.

        Parameters:
            addr (int) -- the full address of the new cache line's entries.
                          Note that the offset does not matter.
            data (int) -- the data to be saved in the cache line.

        Returns:
            This function does not have a return value.
        """
        raise NotImplementedError("Cache Replacement Policy not implemented.")

    def read(self, addr: int, side_effects=True) -> Optional[int]:
        """
        Returns the data at address addr as an integer.
        If no data is cached for this address, None is returned.

        Parameters:
            addr (int) -- the address from which to read
            side_effects (bool) -- whether the read should
                have an effect on caches that use access
                times for their replacement policy, like LRU.

        Returns:
            int: The cached data.
            Returns 'None' if 'addr' is not cached.
        """

        tag, index, offset = self.parse_addr(addr)

        for i in range(self.num_lines):
            if self.sets[index][i].check_tag(tag):
                return self.sets[index][i].read(offset, side_effects)

        return None

    def write(self, addr: int, data: int, side_effects: bool = True) -> None:
        """
        Adds 'data' to the cache, indexed by 'addr'.
        If required, the replacement policy is applied.

        Parameters:
            addr (int) -- the address to which to write
            data (int) -- the data to cache
            side_effects (bool) -- whether the write should
                have an effect on caches that use access times
                for thei replacement policy, like LRU.

        Returns:
            This function does not have a return value.
        """
        tag, index, offset = self.parse_addr(addr)

        # check if all cache lines of the corresponding cache
        # set are already in use.
        for i in range(self.num_lines):
            if not self.sets[index][i].is_in_use():
                self.sets[index][i].set_tag(tag)
            if self.sets[index][i].check_tag(tag):
                self.sets[index][i].write(offset, data, side_effects)
                return

        # apply replacement policy of all cache lines are in use
        self._apply_replacement_policy(addr, data)

    def flush(self, addr: int) -> None:
        """
        Removes the data indexed by 'addr' from the cache.

        Parameters:
            addr (int) -- the address to be flushed from the cache

        Returns:
            This function does not have a return value.
        """

        tag, index, offset = self.parse_addr(addr)

        for i in range(self.num_lines):
            if self.sets[index][i].check_tag(tag):
                self.sets[index][i].flush()
                return

    def flush_all(self) -> None:
        """Removes all data from the cache."""
        for i in range(self.num_sets):
            for j in range(self.num_lines):
                if self.sets[i][j].is_in_use():
                    self.sets[i][j].flush()

    def get_num_sets(self):
        """Returns the number of sets this cache uses."""
        return self.num_sets

    def get_num_lines(self):
        """Returns the number of lines per set."""
        return self.num_lines

    def get_line_size(self):
        """Returns the number of entries per cache line."""
        return self.line_size

    def get_cache_dump(self):
        """
        Returns a dictionary that contains the number of cache sets,
        the number of cache lines per set, and the size of each line.
        Additionally, the dictionary contains an array where each entry
        corresponds to a cache line, whcih also contains the cached
        data.

        This function is intended to be used during testing and for
        visualization purposes by the GUI.

        Returns:
            A dictionary of the following form is returned:
                {
                    "sets": [
                        [
                            {
                                "tag": ... (int),
                                "data": list[int]
                            }
                        ] // each of these entries represents a cache line
                    ],
                    "num_sets": ... (int),
                    "num_lines": ... (int),
                    "line_size": ... (int)
                }
        """

        cache = {
            "sets": [
                [
                    {
                        "data": self.sets[i][j].data,
                        "tag": self.sets[i][j].tag
                    } for j in range(self.num_lines)
                ] for i in range(self.num_sets)],
            "num_sets": self.get_num_sets(),
            "num_lines": self.get_num_lines(),
            "line_size": self.get_line_size()
        }
        return cache


class CacheRR(Cache[CacheLine]):
    """A cache implementing the random replacement policy."""

    def __init__(self, num_sets: int, num_lines: int, line_size: int):
        super().__init__(num_sets, num_lines, line_size, CacheLine)

    def _apply_replacement_policy(self, addr: int, data: int) -> None:
        tag, index, offset = self.parse_addr(addr)

        replaceIndex = random.randrange(self.num_lines)
        self.sets[index][replaceIndex].flush()
        self.sets[index][replaceIndex].set_tag(tag)
        self.sets[index][replaceIndex].write(offset, data)


class CacheLineLRU(CacheLine):
    """
    A helper class representing a cache line in a cache that
    implements the least-recently-used replacement policy.
    """

    # update this variable each time we read/write.
    lru_timestamp: float

    def __init__(self, line_size: int):
        super().__init__(line_size)
        self.lru_timestamp = time()

    def read(self, offset: int, side_effects: bool = True) -> Optional[int]:
        data = super().read(offset)
        if data is not None and side_effects:
            self.lru_timestamp = time()
        return data

    def write(self, offset, data: int, side_effects: bool = True) -> None:
        super().write(offset, data, side_effects)

        if side_effects:
            self.lru_timestamp = time()

    def get_lru_time(self):
        return self.lru_timestamp


class CacheLRU(Cache[CacheLineLRU]):
    """A cache implementing the least-recently-used replacement policy."""

    def __init__(self, num_sets: int, num_lines: int, line_size: int):
        super().__init__(num_sets, num_lines, line_size, CacheLineLRU)

    def _apply_replacement_policy(self, addr: int, data: int) -> None:
        """
        Implements a least-recently-used policy by using the lru_timestamp variable
        from CacheLineLRU.
        """

        tag, index, offset = self.parse_addr(addr)

        lru_index = 0
        lru_time = self.sets[index][0].get_lru_time()
        for i in range(self.num_lines):
            if self.sets[index][i].get_lru_time() < lru_time:
                lru_index = i
                lru_time = self.sets[index][i].get_lru_time()

        self.sets[index][lru_index].flush()
        self.sets[index][lru_index].set_tag(tag)
        self.sets[index][lru_index].write(offset, data)


class CacheLineFIFO(CacheLine):
    """
    A helper class representing a cache line in a cache that
    implements the first-in-first-out replacement policy.
    """

    # update this variable on the first write/on initialization.
    first_write: float

    def __init__(self, line_size: int):
        super().__init__(line_size)
        self.first_write = time()

    def write(self, offset: int, data: int, side_effects: bool = True) -> None:
        if self.data is None and side_effects:
            self.first_write = time()

        super().write(offset, data, side_effects)

    def get_fifo_time(self):
        return self.first_write


class CacheFIFO(Cache[CacheLineFIFO]):
    """A Cache implementing the first-in-first-out replacement policy."""

    def __init__(self, num_sets: int, num_lines: int, line_size: int):
        super().__init__(num_sets, num_lines, line_size, CacheLineFIFO)

    def _apply_replacement_policy(self, addr: int, data: int) -> None:
        """
        Implements a least-recently-used policy by using the first_write variable
        from CacheLineFIFO.
        """

        tag, index, offset = self.parse_addr(addr)

        fifo_index = 0
        fifo_time = self.sets[index][0].get_fifo_time()
        for i in range(self.num_lines):
            if self.sets[index][i].get_fifo_time() < fifo_time:
                fifo_index = i
                fifo_time = self.sets[index][i].get_fifo_time()

        self.sets[index][fifo_index].flush()
        self.sets[index][fifo_index].set_tag(tag)
        self.sets[index][fifo_index].write(offset, data)
