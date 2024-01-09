
from __future__ import annotations

from abc import ABC
from typing import Optional

from .instructions import RegID


def format_entries(values: list, label: str, value_fmt: str = ""):
    result = f"Index | {label}\n"
    result += "------+--------\n"
    for i, v in enumerate(values):
        v_str = "N/A" if v is None else format(v, value_fmt)
        result += f"{i:>5} | {v_str}\n"
    return result


def bimodal_update(state: int, taken: bool) -> int:
    if taken:
        return min(state + 1, 3)
    else:
        return max(state - 1, 0)


def bimodal_prediction(state: int) -> bool:
    return state >= 2


class DirectMappingMixin:
    indexing_bits: int

    def __init__(self, indexing_bits: int):
        self.indexing_bits = indexing_bits

    def pc_to_index(self, pc: int) -> int:
        return (pc >> 2) % (1 << self.indexing_bits)


class AbstractBPU(ABC):
    def __init__(self, config):
        pass

    def update(self, pc: int, taken: bool) -> None:
        raise NotImplementedError

    def predict(self, pc: int) -> bool:
        raise NotImplementedError

    def set_counter(self, pc: int, val: int) -> None:
        raise NotImplementedError


class AbstractBTB(ABC):
    def __init__(self, config):
        pass

    def update(self, pc: int, jumped_to: int) -> None:
        raise NotImplementedError

    def predict(self, pc: int) -> int:
        raise NotImplementedError

    def set_entry(self, pc: int, val: int) -> None:
        raise NotImplementedError


class AbstractRSB(ABC):
    def __init__(self, config):
        pass

    def push(self, addr: int) -> None:
        raise NotImplementedError

    def pop(self) -> Optional[int]:
        raise NotImplementedError

    def handle(self, pc: int, dest_reg: Optional[RegID], link_reg: RegID) -> Optional[int]:
        raise NotImplementedError


class BPU(AbstractBPU, DirectMappingMixin):
    counters: list[int]

    def __init__(self, config) -> None:
        DirectMappingMixin.__init__(self, config["BPU"]["index_bits"])
        self.counters = [config["BPU"]["init_counter"]] * (1 << self.indexing_bits)

    def update(self, pc: int, taken: bool) -> None:
        idx = self.pc_to_index(pc)
        self.counters[idx] = bimodal_update(self.counters[idx], taken)

    def predict(self, pc: int) -> bool:
        return bimodal_prediction(self.counters[self.pc_to_index(pc)])

    def set_counter(self, pc: int, val: int) -> None:
        self.counters[self.pc_to_index(pc)] = val

    def __str__(self) -> str:
        return format_entries(self.counters, "Counter")


class SimpleBPU(AbstractBPU):
    counter: int

    def __init__(self, config) -> None:
        try:
            self.counter = config["BPU"]["init_counter"]
        except KeyError:
            self.counter = 2

    def update(self, pc, taken: bool) -> None:
        self.counter = bimodal_update(self.counter, taken)

    def predict(self, pc) -> bool:
        return bimodal_prediction(self.counter)

    def set_counter(self, pc, val: int) -> None:
        self.counter = val

    def __str__(self) -> str:
        return str(self.counter)


class BTB(AbstractBTB, DirectMappingMixin):
    entries: list[Optional[int]]

    def __init__(self, config):
        try:
            indexing_bits = config["BPU"]["BTB"]["index_bits"]
        except KeyError:
            indexing_bits = config["BPU"]["index_bits"]
        DirectMappingMixin.__init__(self, indexing_bits)
        self.entries = [None] * (1 << self.indexing_bits)

    def update(self, pc: int, jumped_to: int) -> None:
        self.entries[self.pc_to_index(pc)] = jumped_to

    def predict(self, pc: int) -> int:
        value = self.entries[self.pc_to_index(pc)]
        # If we have no predicted address, pretend we don't know that this is
        # a jump.
        return pc + 4 if value is None else value

    def set_entry(self, pc: int, val: int) -> None:
        self.entries[self.pc_to_index(pc)] = val

    def __str__(self) -> str:
        return format_entries(self.entries, "Address", "#x")


class RSB(AbstractRSB):
    max_depth: int
    entries: list[int]

    RETURN_REGISTERS: frozenset[RegID] = frozenset((RegID(1), RegID(5)))

    def __init__(self, config):
        try:
            self.max_depth = config["BPU"]["RSB"]["max_depth"]
        except KeyError:
            self.max_depth = 1 << config["BPU"]["index_bits"]
        self.entries = []

    def push(self, addr: int) -> None:
        self.entries.append(addr)
        if len(self.entries) > self.max_depth:
            self.entries = self.entries[1:]

    def pop(self) -> Optional[int]:
        return self.entries.pop() if self.entries else None

    def handle(self, pc: int, dest_reg: Optional[RegID], link_reg: RegID) -> Optional[int]:
        # RSB behavior as recommended by the RISC-V standard's (2019-12-13) definition of JAL/JALR.
        return_pc = pc + 4

        if dest_reg is None:
            # JAL can only push.
            if link_reg in self.RETURN_REGISTERS:
                self.push(return_pc)
            return None

        link_is_ret = link_reg in self.RETURN_REGISTERS
        dest_is_ret = dest_reg in self.RETURN_REGISTERS

        # JALR has various possible behaviors.
        if not link_is_ret and not dest_is_ret:
            pass
        elif not link_is_ret:
            return self.pop()
        elif not dest_is_ret:
            self.push(return_pc)
        elif link_reg != dest_reg:
            result = self.pop()
            self.push(return_pc)
            return result
        else:
            self.push(return_pc)
        return None

    def __str__(self) -> str:
        return format_entries(self.entries, "Address", "#x")
