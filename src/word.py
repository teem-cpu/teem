"""`Byte` and `Word` classes to represent 8- and 16-bit values."""

from __future__ import annotations

from typing import Iterable, Sequence, Union


class Byte:
    """
    A byte in the range from 0 to 255.

    The memory contents are made up of individual bytes. Instructions always operate one whole
    `Word`s instead.
    """

    # Width in bits
    WIDTH: int = 8

    # Always in range [0, 255]
    _value: int

    def __init__(self, value: int):
        """Create a new byte from the given unsigned or two's complement signed value."""
        self._value = value % (1 << self.WIDTH)

    @property
    def value(self) -> int:
        """Return this value as an unsigned integer."""
        return self._value

    def zero_extend(self) -> "Word":
        """Zero-extend this byte to the width of a word."""
        return Word(self.value)


class Word:
    """
    A 32-bit value, used for register values and addresses.

    This value can be interpreted as an unsigned integer using `.value`, or as a two's complement
    signed integer using `.signed_value`.
    """

    # Width in bits
    WIDTH: int = 32
    # Width in bytes, rounded upwards
    WIDTH_BYTES: int = (WIDTH + Byte.WIDTH - 1) // Byte.WIDTH
    # Whether we represent a word as little or big endian in memory
    _BIG_ENDIAN: bool = False

    # Always in the range [0, 2**WIDTH)
    _value: int

    def __init__(self, value: int):
        """Create a new word from the given unsigned or two's complement signed value."""
        self._value = value % (1 << self.WIDTH)

    @classmethod
    def from_int(cls, v: Union[int, "Word"]) -> "Word":
        """Convert the given value to a Word, if it is not one yet."""
        return cls(v) if isinstance(v, int) else v

    @classmethod
    def from_bytes_list(cls, bs: Sequence[Byte]) -> Sequence["Word"]:
        """Create multiple word from the given byte sequence."""
        if len(bs) % cls.WIDTH_BYTES != 0:
            raise ValueError(f"Invalid number of bytes: {bs!r}")

        result: list["Word"] = []
        for i in range(0, len(bs), cls.WIDTH_BYTES):
            next_i = i + cls.WIDTH_BYTES
            result.append(cls.from_bytes(bs[i:next_i]))

        return result

    @classmethod
    def from_some_bytes(cls, bs: Sequence[Byte], sign_extend: bool = False) -> "Word":
        """Extend the given byte sequence into a new Word."""
        if len(bs) > cls.WIDTH_BYTES or len(bs) == 0:
            raise ValueError(f"Invalid number of bytes: {bs!r}")

        # Account for endianness.
        bs_order: Iterable[Byte]
        if cls._BIG_ENDIAN:
            bs_order = bs
        else:
            bs_order = reversed(bs)

        # Build up the value.
        value = 0
        for b in bs_order:
            value <<= Byte.WIDTH
            value |= b.value

        # Sign-extend if requested.
        if sign_extend:
            sign_bit = 1 << (len(bs) * Byte.WIDTH - 1)
            value |= -(value & sign_bit)

        return cls(value)

    @classmethod
    def from_bytes(cls, bs: Sequence[Byte]) -> "Word":
        """Create a new word from the given representation in memory."""
        if len(bs) != cls.WIDTH_BYTES:
            raise ValueError(f"Invalid number of bytes: {bs!r}")

        # Sign extension has no effect when bs is WIDTH_BYTES long.
        return cls.from_some_bytes(bs, False)

    @property
    def value(self) -> int:
        """Return this value as an unsigned integer."""
        return self._value

    @property
    def signed_value(self) -> int:
        """Return this value as a two's complement signed integer."""
        if self.value < (1 << (self.WIDTH - 1)):
            return self.value
        return self.value - (1 << self.WIDTH)

    def as_bytes(self) -> Iterable[Byte]:
        """Return the bytes used to represent this value in memory."""
        # Range of byte indices
        r = list(range(self.WIDTH_BYTES))
        # Reverse byte indices if we use big endian
        if self._BIG_ENDIAN:
            r.reverse()

        for b in r:
            # Convert from byte index to bit index
            bit = b * Byte.WIDTH
            # Yield the byte starting at the current bit index
            yield Byte(self.value >> bit)

    def __eq__(self, rhs: object) -> bool:
        if not isinstance(rhs, Word):
            return False
        return self.value == rhs.value

    def __ne__(self, rhs: object) -> bool:
        return not self == rhs

    def __add__(self, rhs: "Word") -> "Word":
        return Word(self.value + rhs.value)

    def __sub__(self, rhs: "Word") -> "Word":
        return Word(self.value - rhs.value)

    def __lshift__(self, rhs: "Word") -> "Word":
        return Word(self.value << rhs.value)

    def __and__(self, rhs: "Word") -> "Word":
        return Word(self.value & rhs.value)

    def __or__(self, rhs: "Word") -> "Word":
        return Word(self.value | rhs.value)

    def __xor__(self, rhs: "Word") -> "Word":
        return Word(self.value ^ rhs.value)

    def __invert__(self) -> "Word":
        return Word(~self.value)

    def __repr__(self) -> str:
        return "Word({:#0{}x})".format(self.value, self.WIDTH // 4 + 2)

    def __hash__(self) -> int:
        return hash(self.value)

    def shift_right_logical(self, amount: "Word") -> "Word":
        return Word(self.value >> amount.value)

    def shift_right_arithmetic(self, amount: "Word") -> "Word":
        return Word(self.signed_value >> amount.value)

    def unsigned_lt(self, rhs: "Word") -> bool:
        return self.value < rhs.value

    def unsigned_le(self, rhs: "Word") -> bool:
        return self.value <= rhs.value

    def unsigned_gt(self, rhs: "Word") -> bool:
        return self.value > rhs.value

    def unsigned_ge(self, rhs: "Word") -> bool:
        return self.value >= rhs.value

    def signed_lt(self, rhs: "Word") -> bool:
        return self.signed_value < rhs.signed_value

    def signed_le(self, rhs: "Word") -> bool:
        return self.signed_value <= rhs.signed_value

    def signed_gt(self, rhs: "Word") -> bool:
        return self.signed_value > rhs.signed_value

    def signed_ge(self, rhs: "Word") -> bool:
        return self.signed_value >= rhs.signed_value


def div_trunc(a: int, b: int) -> int:
    """
    Return the result of dividing a by b according to RISC-V integer division semantics.
    """
    if b == 0:
        return -1
    result = abs(a) // abs(b)
    if (a < 0) ^ (b < 0):
        result = -result
    return result


def rem_trunc(a: int, b: int) -> int:
    """
    Return the remainder of dividing a by b according to RISC-V integer division semantics.
    """
    if b == 0:
        return a
    result = abs(a) % abs(b)
    if a < 0:
        result = -result
    return result
