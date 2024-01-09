import unittest
from src import bpu
from benedict import benedict as bd


class BPUTests(unittest.TestCase):

    def test_simple_bpu(self):
        predictor = bpu.SimpleBPU(bd.from_yaml('config.yml'))
        predictor.update(None, True)
        self.assertIs(predictor.predict(None), True)
        predictor.update(None, False)
        self.assertIs(predictor.predict(None), True)
        predictor.update(None, False)
        self.assertIs(predictor.predict(None), False)
        predictor.update(None, True)
        self.assertIs(predictor.predict(None), True)
        predictor.update(None, True)
        self.assertIs(predictor.predict(None), True)
        print(predictor)

    def test_bpu(self):
        advanced_predictor = bpu.BPU(bd.from_yaml('config.yml'))
        advanced_predictor.update(0, True)
        self.assertIs(advanced_predictor.predict(0), True)
        advanced_predictor.update(4, False)
        self.assertIs(advanced_predictor.predict(4), False)
        self.assertIs(advanced_predictor.predict(68), False)
        print(advanced_predictor)


if __name__ == '__main__':
    unittest.main()
