"""
Frontend for the CPU instruction management.

Holds and manages a queue of instructions.
Instructions are taken from a list provided by the parser
and added to the queue with respect to branch management (bpu).
Instructions can be fetched from the queue, e.g. by reservation stations.
Supports flushing the queue and adding a micro program directly to the queue.
"""


from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from . import instructions
from .bpu import AbstractBPU, AbstractBTB, AbstractRSB


@dataclass
class InstrFrontendInfo:
    '''
    Holds an instruction, e.g. from the instruction list provided by the parser,
    with the additional information needed by the CPU and execution engine.
    Keeps track of the BPU/BTB/RSB prediction for branch/jump instructions at
    the time the instruction is added to the queue.
    '''

    instr: instructions.Instruction
    prediction: Optional[bool]
    addr_prediction: Optional[int]


class Frontend:
    '''
    Holds and manages a queue of at most max_length InstrFrontendInfo objects.
    These contain an instruction from the parser instruction list,
    their respective instruction index from the parser list
    and their bpu prediction at the time they are added to the queue
    if they are a branch instruction.
    An exception to this max length is made when adding micro programs.
    Expects an already initialised bpu (e.g. shallow copy of the bpu from a surrounding cpu class)
    and a list of instructions (e.g. as provided by the Parser in paser.py) upon initilisation.
    Max_length is determined in the config file.
    Uses a program counter pc to keep track of
    the next instruction from the provided instruction list that should be added to the queue.
    '''

    max_length: int
    current_length: int
    pc: int
    pc_bounds: tuple[int, int]
    stalled: bool
    bpu: AbstractBPU
    btb: AbstractBTB
    rsb: AbstractRSB
    instr_list: list[instructions.Instruction]
    instr_queue: deque[InstrFrontendInfo]

    def __init__(self, cpu_bpu: AbstractBPU, cpu_btb: AbstractBTB, cpu_rsb: AbstractRSB,
                 cpu_instr_list: list[instructions.Instruction], entry: int, config: dict) -> None:

        self.max_length = config["InstrQ"]["size"]
        self.current_length = 0
        if cpu_instr_list:
            self.pc = entry
            lower_bound = cpu_instr_list[0].addr
            self.pc_bounds = (lower_bound, lower_bound + len(cpu_instr_list) * 4)
        else:
            self.pc = 0
            self.pc_bounds = (0, 0)
        self.stalled = False
        self.bpu = cpu_bpu
        self.btb = cpu_btb
        self.rsb = cpu_rsb
        self.instr_list = cpu_instr_list
        self.instr_queue = deque()

    def instr_at(self, address: int) -> instructions.Instruction:
        '''
        Returns the instruction at the given address or raises a LookupError.
        '''

        if address % 4 != 0:
            raise LookupError(f'Instruction address {address:#x} misaligned')
        elif not (self.pc_bounds[0] <= address < self.pc_bounds[1]):
            raise LookupError(f'Instruction address {address:#x} out of bounds')

        result = self.instr_list[(address - self.pc_bounds[0]) // 4]
        assert address == result.addr
        return result

    def unstall(self) -> None:
        '''
        Finish an instruction fetching stall induced by a serializing instruction.

        See add_instructions_to_queue() for more details.
        '''

        self.stalled = False

    def add_instructions_to_queue(self) -> None:
        '''
        Fills the queue with the InstrFrontendInfo objects
        for the next instructions from the instruction list, as indicated by the pc.

        Only adds an instruction if max_length is not yet reached and the pc points to
        an existing instruction.
        If the queue is full, the function returns without further effect.

        This function automatically stalls the queue if a serializing instruction
        (including fences, breakpoints, or system calls) is fetched. This is done to
        avoid disturbing the RSB when such an instruction is closely followed by a
        return-like instruction. Once the serializing instruction finishes, the
        frontend must be explicitly unstall()ed. Flushing the queue cancels any
        pending stall.

        If the instruction currently added to the list is a branch or jump instruction,
        the pc for the next instruction is set according to the label/number
        provided by the instruction and the bpu prediction for the branch instruction.
        Important: jump and branching instructions need to be explicitly registered
        using appropriate types, not the more generic InstructionType, in the instruction
        list from the parser.
        For all other instructions, the pc is set to the next instruction in the list.

        Currently, this function interacts directly with the bpu to get predictions.
        This has to be modified if a branch order buffer should be used.
        '''

        while (not self.stalled
               and len(self.instr_queue) < self.max_length
               and self.pc < self.pc_bounds[1]):

            instr: instructions.Instruction = self.instr_at(self.pc)
            prediction: Optional[bool] = None
            addr_prediction: Optional[int] = None

            # this needs to be modified if further jump instruction types are
            # implemented
            if isinstance(instr.ty, instructions.InstrBranch):
                # True if branch was/should be taken.
                prediction = self.bpu.predict(self.pc)

                if prediction:
                    self.pc = instr.ops[-1]
                else:
                    self.pc += 4

            elif isinstance(instr.ty, instructions.InstrJump):
                # Jumps are always taken. The RSB is informed of them (for later related
                # returns), but does not influence the destination address fixed into the
                # instruction. The BTB's attention is not needed as the destination can
                # be perfectly predicted from just the instruction.
                prediction = True
                addr_prediction = instr.ops[-1]
                self.rsb.handle(instr.addr, None, instructions.RegID(instr.ops[0]))
                self.pc = addr_prediction

            elif isinstance(instr.ty, instructions.InstrJumpRegister):
                # Register jumps invoke the RSB and BTB (but are always taken).
                prediction = True
                addr_prediction = self.rsb.handle(instr.addr, instructions.RegID(instr.ops[1]),
                                                  instructions.RegID(instr.ops[0]))
                if addr_prediction is None:
                    addr_prediction = self.btb.predict(instr.addr)
                self.pc = addr_prediction

            elif isinstance(instr.ty, instructions.InstrSerializing):
                # Stall instruction fetching to avoid upsetting the RSB.
                self.stalled = True
                self.pc += 4

            else:
                self.pc += 4

            instr_info = InstrFrontendInfo(instr, prediction, addr_prediction)
            self.instr_queue.append(instr_info)

    def add_micro_program(self, micro_prog: list[instructions.Instruction]) -> None:
        '''
        Adds a list of instructions with their info as a µ-program to the queue.
        The queue is not automatically flushed.
        This can be done separately as a "mitigation" against Meltdown.
        The max_length of the queue is disregarded when adding the µ-program,
        so µ-programs can be arbitrarily long and added to full queues.
        If the µ-code contains jump instructions,
        the pc will be set according to the last of these jump instructions.
        The BPU does not affect the µ-program and the jump is always taken.
        The respective instruction index is -1 for all instructions in the µ-program.
        '''

        for current_instr in micro_prog:
            current_instr_info = InstrFrontendInfo(current_instr, None, None)
            self.instr_queue.append(current_instr_info)

            if isinstance(current_instr.ty, instructions.InstrJumpRegister):
                raise Exception(f"Unsupported instruction kind {current_instr.ty} in microprogram")

            elif isinstance(current_instr.ty, (instructions.InstrBranch, instructions.InstrJump)):
                self.pc = current_instr.ops[-1]

    def add_instructions_after_branch(self, taken: bool, instr_addr: int) -> None:
        '''
        Takes the index of a branch instruction in the instruction list
        and a boolen whether or not this branch should be taken as arguments.
        Fills the rest of the instruction queue accordingly
        without adding the branch instruction again.
        Does not automatically flush the queue beforehand.
        '''

        # sanity check, should always be the case
        assert self.pc_bounds[0] <= instr_addr < self.pc_bounds[1]

        current_instr: instructions.Instruction = self.instr_at(instr_addr)

        # sanity check, should always be the case
        # this needs to be modified if further jump instruction types are
        # implemented
        if not isinstance(current_instr.ty, (instructions.InstrBranch, instructions.InstrJumpRegister)):
            raise TypeError(f"Instruction at {instr_addr:x} is not a branch/jump")

        if taken:
            self.pc = current_instr.ops[-1]
        else:
            self.pc = instr_addr + 4

        self.add_instructions_to_queue()

    def pop_instruction_from_queue(self) -> InstrFrontendInfo:
        '''
        Deletes the first (current first in) instruction with it's info
        from the instruction queue and returns it.
        '''

        if not self.instr_queue:
            raise LookupError("instruction queue is empty")

        return self.instr_queue.popleft()

    def fetch_instruction_from_queue(self) -> InstrFrontendInfo:
        '''
        Returns the first (current first in) instruction with it's info
        from the instruction queue.
        It is are not deleted from the queue.
        '''

        if not self.instr_queue:
            raise LookupError("instruction queue is empty")

        return self.instr_queue[0]

    def pop_refill(self) -> InstrFrontendInfo:
        '''
        Pop the first instruction from the queue
        and automatically refill the queue with
        the next instruction(s).
        Does not handle any raised exceptions.
        '''

        current_instr = self.pop_instruction_from_queue()
        self.add_instructions_to_queue()
        return current_instr

    def get_instr_queue_size(self):
        '''
        Returns the number of instructions currently scheduled in the instruction queue.
        '''

        return len(self.instr_queue)

    def flush_instruction_queue(self) -> None:
        '''
        Empties the instruction queue.
        Does not adjust the pc. This has to be done separately, otherwise the instructions
        that were flushed from the queue will be silently skipped.
        Also cancels any ongoing stall.
        '''

        self.instr_queue.clear()
        self.stalled = False

    def set_pc(self, new_pc: int) -> None:
        '''
        Provides an interface to change the program counter
        to an arbitrary position within the instruction list.
        Does not consider or change the instructions which are already in the instruction queue.
        '''

        if new_pc % 4 != 0:
            raise IndexError("new pc misaligned")
        elif not (self.pc_bounds[0] <= new_pc <= self.pc_bounds[1]):
            raise IndexError("new pc out of range")

        self.pc = new_pc

    def get_pc(self) -> int:
        '''
        Interface to retrieve the current value of the program counter.
        '''

        return self.pc

    def is_done(self) -> bool:
        '''
        Returns true if the frontend has fully handled the program,
        i.e. has reached the end of the instr_list
        and all instructions and their info have been removed from the queue.
        This status can reverse from True to False, e.g. if
        µ-programs are added, instructions are added after a branch
        or the pc is adjusted via set_pc.
        '''

        return self.pc >= self.pc_bounds[1] and not self.instr_queue
