"""
Assembly code parser, used to convert assembly code with labels into a list of instructions.

Before any code can be parsed, the available instruction types have to be registered with the
parser.
"""

from __future__ import annotations

from ast import literal_eval
from dataclasses import dataclass
from functools import wraps
from struct import pack
from typing import Callable, List, Literal, Optional, Union, cast
import re

from .instructions import Instruction, InstructionKind, InstructionAlias
from .instructions import ExtOperandKind, RegID, all_instructions_and_aliases


LabelTransform = Literal['lo', 'hi']


REGISTER_NAMES = {
    'zero': 'x0',
    'ra': 'x1', 'sp': 'x2', 'gp': 'x3', 'tp': 'x4',
    't0': 'x5', 't1': 'x6', 't2': 'x7',
    'fp': 'x8', 's0': 'x8', 's1': 'x9',
    'a0': 'x10', 'a1': 'x11', 'a2': 'x12', 'a3': 'x13',
    'a4': 'x14', 'a5': 'x15', 'a6': 'x16', 'a7': 'x17',
    's2': 'x18', 's3': 'x19', 's4': 'x20', 's5': 'x21', 's6': 'x22',
    's7': 'x23', 's8': 'x24', 's9': 'x25', 's10': 'x26', 's11': 'x27',
    't3': 'x28', 't4': 'x29', 't5': 'x30', 't6': 'x31'
}

# x8/s0/fp has two aliases; we pick s0.
REV_REGISTER_NAMES = {v: k for k, v in REGISTER_NAMES.items() if k != 'fp'}


SECTION_ALIASES = {
    '.sdata': '.data',
    '.bss': '.data',
    '.sbss': '.data',
    '.rodata': '.data',
    '.note': None
}


INPUT_LINE_RE = re.compile(
    # Label
    r'\A(?:\s*(?P<label>[A-Za-z_.$][A-Za-z0-9_.$]*):)?'
    # Machine instruction or assembler directive
    r'(?:\s*(?P<instruction>[A-Za-z.][A-Za-z0-9_.]*)(?:\s+(?P<operands>.*?\S))?)?'
    # Comment
    r'(?:\s*(?:#|//).*)?'
    # Trailing whitespace (or a whitespace-only line)
    r'\s*\Z'
)

OPERAND_RE = re.compile(
    # A bare word (with somewhat lax syntax) or a C-like string literal
    r'\s*(?P<value>[^",\\\s]*|"(?:[^"\\]|\\.)*")'
    # Either the next operand or the end of the list
    r'\s*(?:,\s*|\Z)'
)

INTEGER_RE = re.compile(r'\A-?(?:[0-9]+|0[bB][01]+|0[xX][0-9a-fA-F]+)\Z')

LABEL_REFERENCE_RE = re.compile(
    r'\A(?:%(?P<modifier>\w+)\()?'
    r'(?P<label>[A-Za-z0-9_.$]+)?'
    r'(?(modifier)\))\Z'
)

MEMORY_REFERENCE_RE = re.compile(
    r'\A(?!\Z)(?P<full_offset>(?:%(?P<modifier>\w+)\()?'
    r'(?P<offset>-?[A-Za-z0-9_.$]+)?'
    r'(?(modifier)\)))?'
    r'(?:\((?P<register>[A-Za-z0-9]+)\))?\Z'
)


@dataclass
class Label:
    """An assembly label."""
    name: str
    section: str
    offset: int
    line: int


@dataclass
class LabelRef:
    """An unresolved reference to a label."""
    name: str
    section: Optional[str]
    transform: Optional[LabelTransform]
    line: int


ParsedOperand = Union[int, RegID, LabelRef]


@dataclass
class AssemblerInstruction:
    """The in-assembler representation of an instruction with additional metadata."""

    line: int
    addr: int
    ty: InstructionKind
    ops: list[ParsedOperand]

    def to_instruction(self) -> Instruction:
        """Convert this AssemblerInstruction into an executable Instruction."""
        assert all(isinstance(op, int) for op in self.ops)
        return Instruction(self.addr, self.ty, cast(List[int], self.ops))


DirectiveHandler = Callable[["Parser", str, List[str]], None]

DIRECTIVES: dict[str, Optional[DirectiveHandler]] = {}


def directive(
    name: str,
    min_ops: Optional[int] = None,
    max_ops: Optional[int] = None
) -> Callable[[DirectiveHandler], DirectiveHandler]:
    """Decorator for defining a new assembler directive."""
    def callback(func: DirectiveHandler) -> DirectiveHandler:
        @wraps(func)
        def handler(parser: Parser, name: str, ops: list[str]) -> None:
            if min_ops is not None and len(ops) < min_ops:
                raise parser.error(f'Too few operands for directive {name}: '
                                   f'Expected at least {min_ops}, got {len(ops)}')

            if max_ops is not None and len(ops) > max_ops:
                raise parser.error(f'Too many operands for directive {name}: '
                                   f'Expected at most {max_ops}, got {len(ops)}')

            func(parser, name, ops)

        DIRECTIVES[name] = handler
        return func

    return callback


def ignore_directive(name: str) -> None:
    """Register a directive type to be handled by doing nothing."""
    DIRECTIVES[name] = None


@directive('.text')
@directive('.data')
@directive('.bss')
@directive('.section', min_ops=1)
def d_switch_section(parser: Parser, name: str, ops: list[str]):
    section: Optional[str]
    if name == '.section':
        raw_section = ops[0]
        if not raw_section.startswith('.'):
            raise parser.error(f'Unsupported nonstandard section name: {raw_section}')
        next_dot = raw_section.find('.', 1)
        section = raw_section if next_dot == -1 else raw_section[:next_dot]
    else:
        section = name

    if section in SECTION_ALIASES:
        section = SECTION_ALIASES[section]

    if section not in ('.text', '.data', None):
        raise parser.error(f'Unsupported section type: {section}')

    parser.current_section = section


@directive('.string')
@directive('.ascii')
@directive('.asciz')
def d_emit_strings(parser: Parser, name: str, ops: list[str]):
    suffix = b'' if name == '.ascii' else b'\0'
    for text in ops:
        parser.emit_data(text.encode('ascii') + suffix)


@directive('.byte')
def d_emit_bytes(parser: Parser, name: str, ops: list[str]):
    for op in ops:
        parser.emit_data(pack('<B', parser.to_int(op) & 0xFF))


@directive('.2byte')
@directive('.half')
@directive('.short')
def d_emit_halfwords(parser: Parser, name: str, ops: list[str]):
    for op in ops:
        parser.emit_data(pack('<H', parser.to_int(op) & 0xFFFF))


@directive('.4byte')
@directive('.word')
@directive('.long')
def d_emit_words(parser: Parser, name: str, ops: list[str]):
    for op in ops:
        op_value_list = parser.parse_instruction_operand('imm', op)
        assert len(op_value_list) == 1

        op_value: Union[bytes, LabelRef]
        if isinstance(op_value_list[0], int):
            op_value = pack('<I', op_value_list[0] & 0xFFFFFFFF)
        else:
            op_value = op_value_list[0]

        parser.emit_data(op_value)


@directive('.8byte')
@directive('.dword')
@directive('.quad')
def d_emit_doublewords(parser: Parser, name: str, ops: list[str]):
    for op in ops:
        parser.emit_data(pack('<Q', parser.to_int(op) & 0xFFFFFFFFFFFFFFFF))


@directive('.zero', min_ops=1, max_ops=1)
def d_emit_zeros(parser: Parser, name: str, ops: list[str]):
    parser.emit_data(b'\0' * parser.to_int(ops[0]))


@directive('.p2align', min_ops=1, max_ops=3)
@directive('.balign', min_ops=1, max_ops=3)
def d_align(parser: Parser, name: str, ops: list[str]):
    alignment = 0 if len(ops) <= 0 else parser.to_int(ops[0])
    fill = None if len(ops) <= 1 else parser.to_int(ops[1])
    maximum = None if len(ops) <= 2 else parser.to_int(ops[2])

    if name == '.p2align':
        alignment = 1 << alignment

    parser.emit_align(alignment, fill, maximum)


@directive('.comm', min_ops=2, max_ops=3)
def d_comm(parser: Parser, name: str, ops: list[str]):
    symbol = ops[0]
    size = parser.to_int(ops[1])
    alignment = None if len(ops) <= 2 else parser.to_int(ops[2])

    if alignment is None:
        alignment = 1
        while 2 * alignment <= size and alignment < 16:
            alignment *= 2

    prev_section = parser.current_section
    parser.current_section = '.data'
    parser.emit_align(alignment)
    parser.make_label(symbol)
    parser.emit_data(b'\0' * size)
    parser.current_section = prev_section


ignore_directive('.file')
ignore_directive('.globl')
ignore_directive('.weak')
ignore_directive('.local')
ignore_directive('.ident')
ignore_directive('.type')
ignore_directive('.size')
ignore_directive('.attribute')

ignore_directive('.addrsig')
ignore_directive('.addrsig_sym')


@dataclass
class LoadSegment:
    """A ready-to-load segment of program memory."""
    address: int
    data: bytes
    code: Optional[list[Instruction]] = None


class Section:
    """A section of prospective assembler output."""

    address: int
    data: list[Union[bytes, LabelRef]]
    length: int

    def __init__(self):
        """Create a new instance."""
        self.address = 0
        self.data = []
        self.length = 0

    def __bytes__(self) -> bytes:
        """Pack the entire section into a byte string."""
        for d in self.data:
            if not isinstance(d, bytes):
                raise ValueError(f'Section has unresolved references (first from line #{d.line})')
        return b''.join(cast(List[bytes], self.data))

    def __len__(self) -> int:
        """Return the offset of the current end of the section."""
        return self.length

    def append(self, data: Union[bytes, LabelRef]):
        """Append bytes to the section."""
        self.data.append(data)
        if isinstance(data, bytes):
            self.length += len(data)
        else:
            self.length += 4

    def align(self, alignment: int, fill: Optional[int] = None,
              maximum: Optional[int] = None):
        """
        Align the current end of the section.

        Parameters:
            alignment (int) -- Align to a multiple of this number. If zero, no alignment is done.
            fill (int or None) -- Use this byte value for alignment bytes. If None, zero bytes are
                used in data sections.
            maximum (int or None) -- If the required amount of alignment bytes is greater than
                this number, do not align at all.
        """
        if not alignment:
            return
        if fill is None:
            fill = 0

        if self.address % alignment != 0:
            raise RuntimeError('Trying to over-align a section')

        skip = -len(self) % alignment
        if maximum is not None and skip > maximum:
            return
        self.append(bytes((fill,) * skip))

    def to_segment(self) -> LoadSegment:
        """Convert this section into a loadable segment."""
        return LoadSegment(self.address, bytes(self))


class CodeSection:
    """
    An assembly section containing "machine code".

    Since we do not manage actual machine code, this cannot be just another
    section.
    """

    @staticmethod
    def _dummy_instruction(addr):
        """Encode a dummy instruction denoting the given instruction address."""
        # The trailing bits 0101011 are in the "reserved-1" area of the base opcode map.
        # The address is shifted by eight bits to ease reading hexdumps.
        return pack('<I', (addr << 8) | 0x2b)

    address: int
    data: list[AssemblerInstruction]

    def __init__(self):
        """Create a new instance."""
        self.address = 0
        self.data = []

    def __bytes__(self) -> bytes:
        """Return a byte string representing the section's contents."""
        # TODO: Encode into actual machine instructions.
        return b''.join(self._dummy_instruction(instr.addr) for instr in self.data)

    def __len__(self) -> int:
        """Return the offset of the current end of the section."""
        return len(self.data) * 4

    def append(self, instr: AssemblerInstruction):
        """Append an instruction to the section."""
        self.data.append(instr)

    def align(self, alignment: int, fill: Optional[int] = None,
              maximum: Optional[int] = None):
        """
        Align the current end of the section.

        In code sections, this is a dummy function that only validates the alignment argument.
        """
        if alignment % 4 != 0:
            raise ValueError('Code sections should be aligned to a multiple of 4')

    def to_segment(self) -> LoadSegment:
        """
        Convert this section into a loadable segment.

        The addresses of all instructions are fixed up to include this section's base address.
        """
        for n, instr in enumerate(self.data):
            instr.addr = self.address + n * 4
        return LoadSegment(self.address, bytes(self), [ai.to_instruction() for ai in self.data])


@dataclass
class ProgramImage:
    entry_point: int
    text_segment: LoadSegment
    data_segment: LoadSegment
    symbols: dict[str, int]


class Parser:
    """Minimalistic RISC-V assembly parser."""

    instr_types: dict[str, dict[int, Union[InstructionKind, InstructionAlias]]]
    directives: dict[str, Optional[DirectiveHandler]]

    always_reserve_data_bytes: bool

    current_line: int

    current_section: Optional[str]
    text_section: CodeSection
    data_section: Section
    labels: dict[str, Label]
    entry_point: Optional[int]

    @staticmethod
    def parse_register(reg_name: str) -> Optional[RegID]:
        reg_name = reg_name.lower()
        if reg_name in REGISTER_NAMES:
            reg_name = REGISTER_NAMES[reg_name]
        elif not reg_name.startswith('x') and not reg_name.startswith('r'):
            return None
        reg_id = int(reg_name[1:])
        if not (0 <= reg_id < 32):
            return None
        return RegID(reg_id)

    def __init__(self):
        """Create a new parser without knowledge of any instructions or directives."""
        self.always_reserve_data_bytes = True
        self.instr_types = {}
        self.directives = {}
        self.current_line = 0
        self.text_section = CodeSection()
        self.data_section = Section()
        self.current_section = '.text'
        self.labels = {}
        self.entry_point = None

    @classmethod
    def from_default(cls) -> Parser:
        """Create a new parser with knowledge of our instruction set and standard directives."""
        p = cls()
        for instr in all_instructions_and_aliases:
            p.add_instruction(instr)
        for name, handler in DIRECTIVES.items():
            p.add_directive(name, handler)
        return p

    def add_instruction(self, instr: Union[InstructionKind, InstructionAlias]):
        """Add an instruction type to this parser."""
        self.instr_types.setdefault(instr.name, {})[len(instr.operand_types)] = instr

    def add_directive(self, name: str, handler: Optional[DirectiveHandler]):
        """Add a directive handler to this parser."""
        self.directives[name] = handler

    def get_section(self, name: str) -> Union[Section, CodeSection]:
        """Return the section with the given name."""
        if name == '.text':
            return self.text_section
        elif name == '.data':
            return self.data_section
        else:
            raise LookupError(f'Unknown section {name}')

    def to_int(self, s: str, base: int = 0) -> int:
        """Parse the given string into an integer or raise a syntax error."""
        try:
            return int(s, base)
        except ValueError as exc:
            raise self.error(str(exc))

    def error(self, message: str, line: Optional[int] = None) -> Exception:
        """Return (but do not raise!) an exception denoting a syntax error."""
        if line is None:
            line = self.current_line

        return ValueError(f'Line #{line}: {message}')

    def make_label(self, name: str) -> Label:
        """Construct and store a Label denoting the current output position."""
        if name in self.labels:
            raise self.error(f'Duplicate label: {name}')

        if self.current_section is None:
            raise self.error('Labels in an ignored section are not supported')

        offset: int
        if self.current_section == '.text':
            offset = len(self.text_section)
        else:
            offset = len(self.data_section)

        result = Label(name, self.current_section, offset, self.current_line)
        self.labels[name] = result
        return result

    def emit_data(self, data: Union[bytes, LabelRef]):
        """Append the given bytes to the current section."""
        if self.current_section is None:
            raise self.error('Data in an ignored section are not supported')
        elif self.current_section == '.text':
            raise self.error('Data in the .text section are not supported')

        self.data_section.append(data)

    def emit_align(self, alignment: int, fill: Optional[int] = None,
                   maximum: Optional[int] = None):
        """Align the current size of the current section to a multiple of the given alignment."""
        if self.current_section == '.text':
            self.text_section.align(alignment, fill, maximum)
        elif self.current_section == '.data':
            self.data_section.align(alignment, fill, maximum)

    def parse_directive(self, name: str, operands: list[str]):
        """Parse the given assembler directive and apply its effects."""
        if name not in self.directives:
            raise self.error(f'Unrecognized directive {name}')

        handler = self.directives[name]
        if handler is None:
            return

        handler(self, name, operands)

    def parse_instruction_operand(self, op_type: ExtOperandKind, op_str: str) -> list[ParsedOperand]:
        """
        Parse the given CPU instruction operand.

        Note that certain operands (viz. memory references) produce multiple values.
        """
        def parse_label_ref(op_str: str, section: Optional[str]) -> LabelRef:
            """Parse the given string into a label reference."""
            m = LABEL_REFERENCE_RE.match(op_str)
            if not m:
                raise self.error(f'Invalid label reference: {op_str}')

            label = m.group('label')
            transform = m.group('modifier')
            if label is not None and INTEGER_RE.match(label):
                raise self.error(f'Invalid label {label} in label reference {op_str}')

            if transform not in (None, 'hi', 'lo'):
                raise self.error(f'Invalid transform {transform} in label reference {op_str}')
            transform = cast(Optional[LabelTransform], transform)

            return LabelRef(label, section, transform, self.current_line)

        def parse_int_or_label_ref(op_str: str, section: Optional[str]) -> Union[int, LabelRef]:
            """Parse the given string into a constant integer or a label reference."""
            if INTEGER_RE.match(op_str):
                return self.to_int(op_str)
            else:
                return parse_label_ref(op_str, section)

        if op_type == 'imm':
            return [parse_int_or_label_ref(op_str, None)]

        elif op_type == 'reg':
            reg_id = self.parse_register(op_str)
            if reg_id is None:
                raise self.error(f'Invalid register name: {op_str}')
            return [reg_id]

        elif op_type in ('code_label', 'data_label'):
            return [parse_label_ref(op_str, ('.text' if op_type == 'code_label' else '.data'))]

        elif op_type == 'memref':
            m = MEMORY_REFERENCE_RE.match(op_str)
            if not m:
                raise self.error(f'Invalid memory operand: {op_str}')

            reg_name = m.group('register') or 'zero'
            register = self.parse_instruction_operand('reg', reg_name)

            raw_offset = m.group('full_offset')
            if raw_offset:
                offset = [parse_int_or_label_ref(raw_offset, None)]
            else:
                offset = [0]

            return register + offset

        else:
            raise AssertionError(f'Unhandled operand type: {op_type}')

    def check_instruction_operand(self, op_type: ExtOperandKind, op_value: ParsedOperand):
        """Ensure the given already-parsed operand matches the given type."""
        if op_type == 'imm':
            return isinstance(op_value, int) or isinstance(op_value, LabelRef)

        elif op_type == 'reg':
            # Under older Pythons, RegID is merely a factory function.
            return isinstance(op_value, int)

        elif op_type in ('code_label', 'data_label'):
            expected_section = ('.text' if op_type == 'code_label' else '.data')
            return isinstance(op_value, LabelRef) and op_value.section == expected_section

        elif op_type == 'memref':
            raise AssertionError('memref operands may not appear in parse results')

        else:
            raise AssertionError(f'Unhandled operand type: {op_type}')

    def parse_instruction(self, instr, operands) -> AssemblerInstruction:
        """Parse and output the given CPU instruction."""
        if self.current_section != '.text':
            raise self.error('CPU instructions in non-code sections are not supported')

        if instr not in self.instr_types:
            raise self.error(f'Unknown instruction type: {instr}')
        ity_map = self.instr_types[instr.lower()]
        if len(operands) not in ity_map:
            raise self.error(f'Instruction type {instr} does not take {len(operands)} operands')
        ity = ity_map[len(operands)]

        if len(operands) != len(ity.operand_types):
            raise self.error(f'Invalid operand count for instruction {instr}: '
                             f'Expected {len(ity.operand_types)}, got {len(operands)}')
        parsed_operands: list[ParsedOperand] = []
        for oty, op in zip(ity.operand_types, operands):
            parsed_operands.extend(self.parse_instruction_operand(oty, op))

        if isinstance(ity, InstructionAlias):
            new_ity = self.instr_types[ity.base_name][len(ity.base_operands)]

            if isinstance(new_ity, InstructionAlias):
                raise AssertionError(f'Recursive instruction aliases are not implemented '
                                     f'({ity.name} => {new_ity.name})')

            new_operands: list[ParsedOperand] = []
            for odef, oty in zip(ity.base_operands, new_ity.operand_types):
                if isinstance(odef, int):
                    op = parsed_operands[odef]
                    if not self.check_instruction_operand(oty, op):
                        raise AssertionError(f'Instruction alias {ity.name} has mis-typed operand mappings')
                    new_operands.append(op)
                else:
                    new_operands.extend(self.parse_instruction_operand(oty, odef))

            ity, parsed_operands = new_ity, new_operands

        result = AssemblerInstruction(self.current_line, len(self.text_section), ity, parsed_operands)
        self.text_section.append(result)
        return result

    def read_operands(self, ops_str: str) -> list[str]:
        """Decode the given list of instruction or directive operands."""
        if not ops_str or ops_str.isspace():
            return []

        index = 0
        result: list[str] = []
        while index < len(ops_str):
            m = OPERAND_RE.match(ops_str, index)
            if not m:
                raise self.error(f'Invalid operand #{len(result) + 1}: {ops_str[index:]!r}')
            index = m.end()

            raw_value = m.group('value')
            if raw_value.startswith('"'):
                try:
                    result.append(literal_eval(raw_value))
                except SyntaxError as exc:
                    raise self.error(f'Invalid operand #{len(result) + 1}: {exc}')
            else:
                result.append(raw_value)

        return result

    def read(self, src: str):
        """Read and assemble the given source string."""
        for i, line in enumerate(src.split('\n'), 1):
            self.current_line = i
            m = INPUT_LINE_RE.match(line)
            if not m:
                raise self.error(f'Invalid syntax: {line!r}')
            label, instr, raw_operands = m.group('label', 'instruction', 'operands')

            if label:
                self.make_label(label)

            if instr:
                operands = self.read_operands(raw_operands or '')

                if instr.startswith('.'):
                    self.parse_directive(instr, operands)
                else:
                    self.parse_instruction(instr, operands)

    def layout(self) -> None:
        """Determine the program's final memory layout."""
        self.data_section.address = 0
        end_of_data = self.data_section.address + len(self.data_section)

        # Put code and data a bit apart, but try to avoid three-digit instruction addresses
        # in small programs.
        self.text_section.address = (end_of_data + 0x7f) & ~0x7f

    def label_to_addr(self, label: Label) -> int:
        """Resolve the given label to an address."""
        return self.get_section(label.section).address + label.offset

    def resolve(self) -> None:
        """Resolve any outstanding label references."""
        def resolve_label(lr: LabelRef) -> int:
            if lr.name not in self.labels:
                raise self.error(f'Undefined label {lr.name}', line=lr.line)
            label = self.labels[lr.name]

            if lr.section is not None and lr.section != label.section:
                raise self.error(f'Expected label {lr.name} to be in in section {lr.section}, '
                                 f'but it is in {label.section}', line=lr.line)

            value = self.label_to_addr(label)
            if lr.transform == 'lo':
                value &= (1 << 12) - 1
            elif lr.transform == 'hi':
                value >>= 12

            return value

        for instr in self.text_section.data:
            for i, op in enumerate(instr.ops):
                if isinstance(op, LabelRef):
                    instr.ops[i] = resolve_label(op)

        for i, item in enumerate(self.data_section.data):
            if isinstance(item, LabelRef):
                self.data_section.data[i] = pack('<I', resolve_label(item))

        if self.entry_point is None and '_start' in self.labels:
            self.entry_point = resolve_label(LabelRef('_start', '.text', None, 0))
        if self.entry_point is None:
            self.entry_point = self.get_section('.text').address

    def parse(self, src: str) -> ProgramImage:
        """
        Fully parse and assemble the given source string.

        This read()s the string, layout()s the sections, resolve()s label references, and
        outputs a ready-to-use ProgramImage.
        """
        if self.always_reserve_data_bytes:
            # Reserve a small amount of data bytes to account for
            # (1) assembler programs that do not declare their data, and
            # (2) C programs that might dislike having variables whose address is NULL.
            self.data_section.append(b'\0\0\0\0')

        self.read(src)
        self.layout()
        self.resolve()
        assert self.entry_point is not None
        return ProgramImage(
            self.entry_point,
            self.text_section.to_segment(),
            self.data_section.to_segment(),
            {label.name: self.label_to_addr(label) for label in self.labels.values()}
        )
