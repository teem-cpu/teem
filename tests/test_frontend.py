import unittest
from src.frontend import Frontend
import logging
import sys
from benedict import benedict as bd

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(stream_handler)


class FrontendTest(unittest.TestCase):

    def test_frontend(self):

        # preparations for building a working frontend
        from src import bpu, parser, instructions
        full_conf = bd.from_yaml('config.yml')
        cpu_bpu = bpu.BPU(full_conf)
        addi = instructions.all_instructions["addi"]
        beq = instructions.all_instructions["beq"]
        p = parser.Parser()
        p.always_reserve_data_bytes = False
        p.add_instruction(addi)
        p.add_instruction(beq)
        instrs = p.parse('''
            a:
            addi r1, r0, 100
            addi r1, r0, 99
            beq r0, r0, a
            addi r1, r0, 98
            addi r1, r0, 97
        ''').text_segment.code
        cpu_bpu.update(8, True)

        # build frontend
        conf = {"InstrQ": {"size": 3}}
        front = Frontend(cpu_bpu, bpu.BTB(full_conf), bpu.RSB(full_conf),
                         instrs, instrs[0].addr, conf)

        # check raised errors when queue is empty
        with self.assertRaises(Exception) as context:
            front.pop_instruction_from_queue()
        self.assertIn('instruction queue is empty', str(context.exception))

        with self.assertRaises(Exception) as context:
            front.fetch_instruction_from_queue()
        self.assertIn('instruction queue is empty', str(context.exception))

        self.assertFalse(front.is_done())

        # check that the queue is filled but not overfilled
        # check function get_instr_queue_size
        front.add_instructions_to_queue()

        self.assertEqual(front.get_instr_queue_size(), 3)
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, instrs[0])
        self.assertIs(front.instr_queue[1].instr, instrs[1])
        self.assertIs(front.instr_queue[2].instr, instrs[2])

        # check that the instruction addresses are set correctly
        self.assertIs(front.instr_queue[0].instr.addr, 0)
        self.assertIs(front.instr_queue[1].instr.addr, 4)
        self.assertIs(front.instr_queue[2].instr.addr, 8)

        # check that the predictions are set correctly
        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, None)
        self.assertIs(front.instr_queue[2].prediction, True)

        # check that trying to add instructions to a full queue does not change
        # the queue
        front.add_instructions_to_queue()

        self.assertEqual(front.get_instr_queue_size(), 3)
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, instrs[0])
        self.assertIs(front.instr_queue[1].instr, instrs[1])
        self.assertIs(front.instr_queue[2].instr, instrs[2])

        # check that the instruction addresses are set correctly
        self.assertIs(front.instr_queue[0].instr.addr, 0)
        self.assertIs(front.instr_queue[1].instr.addr, 4)
        self.assertIs(front.instr_queue[2].instr.addr, 8)

        # check that the predictions are set correctly
        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, None)
        self.assertIs(front.instr_queue[2].prediction, True)

        # check handling of jump instruction and get_pc function
        self.assertEqual(front.get_pc(), front.pc)
        self.assertEqual(front.get_pc(), 0)

        # fetching should return the first instruction with its index and leave
        # the queues unchanged
        next_instr = front.fetch_instruction_from_queue()

        self.assertIs(next_instr.instr, instrs[0])
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, instrs[0])
        self.assertIs(front.instr_queue[1].instr, instrs[1])
        self.assertIs(front.instr_queue[2].instr, instrs[2])

        self.assertIs(front.instr_queue[0].instr.addr, 0)
        self.assertIs(front.instr_queue[1].instr.addr, 4)
        self.assertIs(front.instr_queue[2].instr.addr, 8)

        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, None)
        self.assertIs(front.instr_queue[2].prediction, True)

        # popping should return the first instruction and remove it from the
        # queue
        next_instr_two = front.pop_instruction_from_queue()

        self.assertIs(next_instr_two.instr, instrs[0])
        self.assertEqual(len(front.instr_queue), 2)
        self.assertIs(front.instr_queue[0].instr, instrs[1])
        self.assertIs(front.instr_queue[1].instr, instrs[2])

        self.assertIs(next_instr_two.instr.addr, 0)
        self.assertIs(front.instr_queue[0].instr.addr, 4)
        self.assertIs(front.instr_queue[1].instr.addr, 8)

        # flushing should empty the queues
        front.flush_instruction_queue()

        self.assertEqual(front.get_instr_queue_size(), 0)
        self.assertEqual(len(front.instr_queue), 0)

        # check correct handling of branch instruction when no jump is
        # predicted
        cpu_bpu.update(8, False)
        cpu_bpu.update(8, False)
        front.add_instructions_to_queue()
        next_instr_three = front.pop_instruction_from_queue()
        front.add_instructions_to_queue()

        self.assertIs(next_instr_three.instr, instrs[0])
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, instrs[1])
        self.assertIs(front.instr_queue[1].instr, instrs[2])
        self.assertIs(front.instr_queue[2].instr, instrs[3])

        self.assertIs(next_instr_three.instr.addr, 0)
        self.assertIs(front.instr_queue[0].instr.addr, 4)
        self.assertIs(front.instr_queue[1].instr.addr, 8)
        self.assertIs(front.instr_queue[2].instr.addr, 12)

        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, False)
        self.assertIs(front.instr_queue[2].prediction, None)

        # check handling of µ-progrm
        micro_program = [
            instructions.Instruction(-1, addi, [1, 1, 2]),
            instructions.Instruction(-1, beq, [0, 0, 4])
        ]
        front.add_micro_program(micro_program)

        self.assertEqual(front.get_instr_queue_size(), 5)
        self.assertEqual(len(front.instr_queue), 5)
        self.assertIs(front.instr_queue[0].instr, instrs[1])
        self.assertIs(front.instr_queue[1].instr, instrs[2])
        self.assertIs(front.instr_queue[2].instr, instrs[3])
        self.assertIs(front.instr_queue[3].instr, micro_program[0])
        self.assertIs(front.instr_queue[4].instr, micro_program[1])

        self.assertIs(front.instr_queue[0].instr.addr, 4)
        self.assertIs(front.instr_queue[1].instr.addr, 8)
        self.assertIs(front.instr_queue[2].instr.addr, 12)
        self.assertIs(front.instr_queue[3].instr.addr, -1)
        self.assertIs(front.instr_queue[4].instr.addr, -1)

        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, False)
        self.assertIs(front.instr_queue[2].prediction, None)
        self.assertIs(front.instr_queue[3].prediction, None)
        self.assertIs(front.instr_queue[4].prediction, None)

        front.add_instructions_to_queue()

        self.assertEqual(len(front.instr_queue), 5)
        self.assertIs(front.instr_queue[0].instr, instrs[1])
        self.assertIs(front.instr_queue[1].instr, instrs[2])
        self.assertIs(front.instr_queue[2].instr, instrs[3])
        self.assertIs(front.instr_queue[3].instr, micro_program[0])
        self.assertIs(front.instr_queue[4].instr, micro_program[1])

        self.assertIs(front.instr_queue[0].instr.addr, 4)
        self.assertIs(front.instr_queue[1].instr.addr, 8)
        self.assertIs(front.instr_queue[2].instr.addr, 12)
        self.assertIs(front.instr_queue[3].instr.addr, -1)
        self.assertIs(front.instr_queue[4].instr.addr, -1)

        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, False)
        self.assertIs(front.instr_queue[2].prediction, None)
        self.assertIs(front.instr_queue[3].prediction, None)
        self.assertIs(front.instr_queue[4].prediction, None)

        # check jump out of µ-prog
        _ = front.pop_instruction_from_queue()
        _ = front.pop_instruction_from_queue()
        _ = front.pop_instruction_from_queue()
        front.add_instructions_to_queue()

        self.assertEqual(front.get_pc(), 8)
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, micro_program[0])
        self.assertIs(front.instr_queue[1].instr, micro_program[1])
        self.assertIs(front.instr_queue[2].instr, instrs[1])

        self.assertIs(front.instr_queue[0].instr.addr, -1)
        self.assertIs(front.instr_queue[1].instr.addr, -1)
        self.assertIs(front.instr_queue[2].instr.addr, 4)

        # check adding instructions after branch and pop_refill function
        front.flush_instruction_queue()

        with self.assertRaises(Exception) as context:
            front.add_instructions_after_branch(True, 4)
        self.assertIn('Instruction at 4 is not a branch/jump',
                      str(context.exception))

        front.add_instructions_after_branch(True, 8)

        next_instr_four = front.pop_refill()

        self.assertIs(next_instr_four.instr, instrs[0])
        self.assertEqual(len(front.instr_queue), 3)
        self.assertIs(front.instr_queue[0].instr, instrs[1])
        self.assertIs(front.instr_queue[1].instr, instrs[2])
        self.assertIs(front.instr_queue[2].instr, instrs[3])

        self.assertIs(next_instr_four.instr.addr, 0)
        self.assertIs(front.instr_queue[0].instr.addr, 4)
        self.assertIs(front.instr_queue[1].instr.addr, 8)
        self.assertIs(front.instr_queue[2].instr.addr, 12)

        self.assertIs(next_instr_four.prediction, None)
        self.assertIs(front.instr_queue[0].prediction, None)
        self.assertIs(front.instr_queue[1].prediction, False)
        self.assertIs(front.instr_queue[2].prediction, None)

        # check pc setter
        front.flush_instruction_queue()

        with self.assertRaises(Exception) as context:
            front.set_pc(1)
        self.assertIn('new pc misaligned', str(context.exception))

        with self.assertRaises(Exception) as context:
            front.set_pc(-4)
        self.assertIn('new pc out of range', str(context.exception))

        with self.assertRaises(Exception) as context:
            front.set_pc(24)
        self.assertIn('new pc out of range', str(context.exception))

        front.set_pc(16)
        self.assertEqual(front.get_pc(), 16)

        # check is_done function
        self.assertFalse(front.is_done())
        front.add_instructions_to_queue()
        self.assertFalse(front.is_done())

        front.flush_instruction_queue()
        self.assertTrue(front.is_done())


if __name__ == '__main__':
    unittest.main()
