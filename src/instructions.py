"""All the instructions in our instruction set, and the types used to describe them."""

from __future__ import annotations

import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, NewType, Optional, Union

from .word import Word, div_trunc, rem_trunc

# Possible types of instruction operands
OperandKind = Literal["reg", "imm", "code_label", "data_label"]

# Additional instruction operand kinds only available to aliases
ExtOperandKind = Literal[OperandKind, "memref"]

# ID of a register, used as index into the register file
RegID = NewType("RegID", int)

# The precise behavior of a serializing instruction (aside from serializing the instruction stream)
SerializedEffect = Literal["fence", "ecall", "ebreak"]


class InstructionKind(ABC):
    """Information about a kind of instruction, e.g. `add reg, reg, reg` or `subi reg, reg, imm`."""

    operand_types: list[OperandKind]
    name: str

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"<InstructionKind '{self.name} {', '.join(self.operand_types)}'>"

    @abstractmethod
    def sources(self) -> Iterable[int]:
        """Return the indices of all source operands."""

    @abstractmethod
    def destination(self) -> Optional[int]:
        """Return the index of the destination operand, if any."""


class TimedInstructionKind(InstructionKind):
    """Information about a kind of instructions that includes delay cycles."""

    cycles: int

    def __init__(self, name: str, cycles: int = 1):
        super().__init__(name)

        self.cycles = cycles


class InstrReg(TimedInstructionKind):
    """An ALU instruction that operates solely on registers."""

    operand_types = ["reg", "reg", "reg"]

    # Wrap callable type in `Optional` to prevent `mypy` from mistaking it as a method
    compute_result: Optional[Callable[[Word, Word], Word]]

    def __init__(self, name: str, compute_result: Callable[[Word, Word], Word], cycles: int = 1):
        super().__init__(name, cycles)

        self.compute_result = compute_result

    def sources(self) -> Iterable[int]:
        return [1, 2]

    def destination(self) -> Optional[int]:
        return 0


class InstrImm(TimedInstructionKind):
    """An ALU instruction that takes an immediate operand."""

    operand_types = ["reg", "reg", "imm"]

    # Wrap callable type in `Optional` to prevent `mypy` from mistaking it as a method
    compute_result: Optional[Callable[[Word, Word], Word]]

    def __init__(self, name: str, compute_result: Callable[[Word, Word], Word], cycles: int = 1):
        super().__init__(name, cycles)

        self.compute_result = compute_result

    def sources(self) -> Iterable[int]:
        return [1, 2]

    def destination(self) -> Optional[int]:
        return 0


class InstrLoadImm(TimedInstructionKind):
    """An ALU instruction setting a register from a large immediate operand."""

    operand_types = ["reg", "imm"]

    compute_result: Optional[Callable[[Word, Word], Word]]

    def __init__(self, name: str, compute_result: Callable[[Word, Word], Word], cycles: int = 1):
        super().__init__(name, cycles)

        self.compute_result = compute_result

    def sources(self) -> Iterable[int]:
        return [1]

    def destination(self) -> Optional[int]:
        return 0


class InstrLoad(InstructionKind):
    """A zero- or sign-extended byte/halfword/word memory load instruction."""

    operand_types = ["reg", "reg", "imm"]

    width: int
    signed: bool

    def __init__(self, name: str, width: int, signed: bool):
        super().__init__(name)

        assert width & (width - 1) == 0, 'InstrLoad width must be a power of two'

        self.width = width
        self.signed = signed

    def sources(self) -> Iterable[int]:
        return [1, 2]

    def destination(self) -> Optional[int]:
        return 0

    def address_source_indices(self) -> tuple[int, int]:
        return (0, 1)


class InstrStore(InstructionKind):
    """A byte/halfword/word memory store."""

    operand_types = ["reg", "reg", "imm"]

    width: int

    def __init__(self, name: str, width: int):
        super().__init__(name)

        assert width & (width - 1) == 0, 'InstrStore width must be a power of two'

        self.width = width

    def sources(self) -> Iterable[int]:
        return [0, 1, 2]

    def destination(self) -> Optional[int]:
        return None

    def address_source_indices(self) -> tuple[int, int]:
        return (1, 2)


class InstrFlush(InstructionKind):
    """A flush instruction, flushing a line from the cache."""

    operand_types = ["reg", "imm"]

    width: int

    def __init__(self, name: str):
        super().__init__(name)

        self.width = 4

    def sources(self) -> Iterable[int]:
        return [0, 1]

    def destination(self) -> Optional[int]:
        return None

    def address_source_indices(self) -> tuple[int, int]:
        return (0, 1)


class InstrFlushAll(InstructionKind):
    """A flush all instruction, flushing the whole cache."""

    operand_types: list[OperandKind] = []

    def sources(self) -> Iterable[int]:
        return []

    def destination(self) -> Optional[int]:
        return None


class InstrBranch(TimedInstructionKind):
    """A branch instruction, branching to the destination when the condition is met."""

    operand_types = ["reg", "reg", "code_label"]

    # Wrap callable type in `Optional` to prevent `mypy` from mistaking it as a method
    condition: Optional[Callable[[Word, Word], bool]]

    def __init__(self, name: str, condition: Callable[[Word, Word], bool], cycles: int = 1):
        super().__init__(name, cycles)

        self.condition = condition

    def sources(self) -> Iterable[int]:
        return [0, 1]

    def destination(self) -> Optional[int]:
        return None


class InstrJump(TimedInstructionKind):
    """An unconditional relative jump-and-link instruction."""

    operand_types = ["reg", "code_label"]

    def sources(self) -> Iterable[int]:
        return [1]

    def destination(self) -> Optional[int]:
        return 0


class InstrJumpRegister(TimedInstructionKind):
    """An unconditional register jump-and-link instruction."""

    operand_types = ["reg", "reg", "imm"]

    def sources(self) -> Iterable[int]:
        return [1, 2]

    def destination(self) -> Optional[int]:
        return 0


class InstrCyclecount(InstructionKind):
    """A cyclecount instruction, reading the cycle counter."""

    operand_types = ["reg"]

    def sources(self) -> Iterable[int]:
        return []

    def destination(self) -> Optional[int]:
        return 0


class InstrSerializing(InstructionKind):
    """An instruction serializing all preceding and following instructions."""

    operand_types = []

    effect: SerializedEffect

    def __init__(self, name: str, effect: SerializedEffect):
        super().__init__(name)

        self.effect = effect

    def sources(self) -> Iterable[int]:
        return []

    def destination(self) -> Optional[int]:
        return None


@dataclass
class Instruction:
    """A concrete instruction in program code."""

    addr: int
    ty: InstructionKind
    ops: list[int]

    def sources(self) -> Iterable[tuple[int, OperandKind]]:
        """Return value and type of all source operands."""
        for idx in self.ty.sources():
            yield self.ops[idx], self.ty.operand_types[idx]

    def destination(self) -> Optional[RegID]:
        """Return the destination register, if any."""
        idx = self.ty.destination()
        if idx is None:
            return None
        else:
            assert self.ty.operand_types[idx] == "reg"
            return RegID(self.ops[idx])


class InstructionAlias:
    """An alternative spelling of an instruction for the parser."""

    name: str
    operand_types: list[ExtOperandKind]
    base_name: str
    base_operands: list[Union[str, int]]

    def __init__(self, name: str, operand_types: list[ExtOperandKind],
                 base_name: str, base_operands: list[Union[str, int]]):
        self.name = name
        self.operand_types = operand_types
        self.base_name = base_name
        self.base_operands = base_operands

    def __repr__(self):
        ops_strings = (f'${op}' if isinstance(op, int) else op
                       for op in self.base_operands)
        return (f"<InstructionAlias '{self.name} {', '.join(self.operand_types)}' "
                f"=> '{self.base_name} {', '.join(ops_strings)}'>")


def _all_instructions() -> Iterable[Union[InstructionKind, InstructionAlias]]:
    """Generate all instructions of our ISA."""
    # ALU instructions, with and without immediate operand
    for name, op in [
        ("add", operator.add),
        ("sub", operator.sub),
        ("sll", operator.lshift),
        ("srl", Word.shift_right_logical),
        ("sra", Word.shift_right_arithmetic),
        ("xor", operator.xor),
        ("or", operator.or_),
        ("and", operator.and_),
    ]:
        yield InstrReg(name, op)
        yield InstrImm(name + "i", op)

    for name, iname, op in [
        ("slt", "slti", lambda a, b: Word(a.signed_lt(b))),
        ("sltu", "sltiu", lambda a, b: Word(a.unsigned_lt(b)))
    ]:
        yield InstrReg(name, op)
        yield InstrImm(iname, op)

    yield InstrLoadImm("lui", lambda i, a: i << Word(12))
    yield InstrLoadImm("auipc", lambda i, a: a + (i << Word(12)))

    # M extension
    for name, op, cycles in [
        ("mul", lambda a, b: Word(a.value * b.value), 4),
        ("mulh", lambda a, b: Word((a.signed_value * b.signed_value) >> Word.WIDTH), 6),
        ("mulhu", lambda a, b: Word((a.value * b.value) >> Word.WIDTH), 6),
        ("mulhsu", lambda a, b: Word((a.signed_value * b.value) >> Word.WIDTH), 6),
        ("div", lambda a, b: Word(div_trunc(a.signed_value, b.signed_value)), 8),
        ("divu", lambda a, b: Word(div_trunc(a.value, b.value)), 8),
        ("rem", lambda a, b: Word(rem_trunc(a.signed_value, b.signed_value)), 8),
        ("remu", lambda a, b: Word(rem_trunc(a.value, b.value)), 8),
    ]:
        yield InstrReg(name, op, cycles=cycles)

    # Memory instructions
    yield InstrLoad("lw", Word.WIDTH_BYTES, True)
    yield InstrLoad("lh", 2, True)
    yield InstrLoad("lb", 1, True)
    yield InstrLoad("lhu", 2, False)
    yield InstrLoad("lbu", 1, False)
    yield InstrStore("sw", Word.WIDTH_BYTES)
    yield InstrStore("sh", 2)
    yield InstrStore("sb", 1)

    # Cache management instructions
    # ("x.flushall" does not actually exist, but the vendor-specific extension
    # instruction with the appropriate semantics has an even uglier name.)
    yield InstrFlush("cbo.flush")
    yield InstrFlushAll("x.flushall")

    # Branch instructions
    for name, op in [
        ("beq", operator.eq),
        ("bne", operator.ne),
        ("blt", Word.signed_lt),
        ("ble", Word.signed_le),
        ("bgt", Word.signed_gt),
        ("bge", Word.signed_ge),
        ("bltu", Word.unsigned_lt),
        ("bleu", Word.unsigned_le),
        ("bgtu", Word.unsigned_gt),
        ("bgeu", Word.unsigned_ge),
    ]:
        yield InstrBranch(name, op)

    # Jump instructions
    yield InstrJump("jal")
    yield InstrJumpRegister("jalr")

    # Cyclecount instruction
    yield InstrCyclecount("rdcycle")

    # Misappropriated instruction fence and (non-misappropriated) environment
    # call instructions
    yield InstrSerializing("fence.i", "fence")
    yield InstrSerializing("ecall", "ecall")
    yield InstrSerializing("ebreak", "ebreak")

    # Legacy spellings of branch instructions
    for name in ("blt", "ble", "bgt", "bge"):
        yield InstructionAlias(name + "s", ["reg", "reg", "code_label"],
                               name, [0, 1, 2])

    # Additional data movement/arithmetics
    yield InstructionAlias("li", ["reg", "imm"], "addi", [0, "zero", 1])
    yield InstructionAlias("mv", ["reg", "reg"], "addi", [0, 1, "0"])
    yield InstructionAlias("not", ["reg", "reg"], "xori", [0, 1, "-1"])
    yield InstructionAlias("neg", ["reg", "reg"], "sub", [0, "zero", 1])

    # Additional conditional sets
    yield InstructionAlias("seqz", ["reg", "reg"], "sltiu", [0, 1, "1"])
    yield InstructionAlias("snez", ["reg", "reg"], "sltu", [0, "zero", 1])
    yield InstructionAlias("sltz", ["reg", "reg"], "slt", [0, 1, "zero"])
    yield InstructionAlias("sgtz", ["reg", "reg"], "slt", [0, "zero", 1])

    # Proper spellings of memory accesses
    for name in ("lw", "sw", "lh", "lhu", "sh", "lb", "lbu", "sb"):
        yield InstructionAlias(name, ["reg", "memref"], name, [0, 1, 2])
    yield InstructionAlias("cbo.flush", ["memref"], "cbo.flush", [0, 1])

    # Additional conditional branches
    for comparison in ("eq", "ne", "lt", "le", "gt", "ge", "ltu", "leu", "gtu", "geu"):
        yield InstructionAlias("b" + comparison + "z", ["reg", "code_label"],
                               "b" + comparison, [0, "zero", 1])

    # Unconditional jumps
    yield InstructionAlias("jalr", ["reg", "memref"], "jalr", [0, 1, 2])
    yield InstructionAlias("j", ["code_label"], "jal", ["zero", 0])
    yield InstructionAlias("jal", ["code_label"], "jal", ["ra", 0])
    yield InstructionAlias("jr", ["reg"], "jalr", ["zero", 0, "0"])
    yield InstructionAlias("jalr", ["reg"], "jalr", ["ra", 0, "0"])
    yield InstructionAlias("ret", [], "jalr", ["zero", "ra", "0"])
    # (These are actually two-instruction sequences including AUIPC, but we'll apply
    # a little linker, err, assembler relaxation here... *innocent whistling*)
    yield InstructionAlias("call", ["code_label"], "jal", ["ra", 0])
    yield InstructionAlias("tail", ["code_label"], "jal", ["zero", 0])

    # Legacy spellings of special instructions
    yield InstructionAlias("flush", ["reg", "imm"], "cbo.flush", [0, 1])
    yield InstructionAlias("flush", ["memref"], "cbo.flush", [0, 1])
    yield InstructionAlias("flushall", [], "x.flushall", [])
    yield InstructionAlias("rdtsc", ["reg"], "rdcycle", [0])
    yield InstructionAlias("fence", [], "fence.i", [])

    # Compiler-compatible aliases of special instructions
    yield InstructionAlias("th.dcache.ciall", [], "x.flushall", [])


all_instructions_and_aliases = list(_all_instructions())

all_instructions = {instr.name: instr
                    for instr in all_instructions_and_aliases
                    if isinstance(instr, InstructionKind)}
