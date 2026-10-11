import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.base__mot_motion_wait import MotionLogWaiter


class MotionWaitTests(unittest.TestCase):
    def waiter(self):
        w = MotionLogWaiter.__new__(MotionLogWaiter)
        w.command, w.direction, w.state = (0., -40.), 'MN', 'guide'
        return w

    def test_requires_all_stages(self):
        w = self.waiter()
        self.assertFalse(w.feed('x - Read OK 36'))
        self.assertFalse(w.feed('x - guideOffset(): {"ra offset":0.0,"dec offset":-40.0}'))
        self.assertFalse(w.feed('x - Send MN#'))
        self.assertFalse(w.feed('x - Read OK 27'))
        self.assertFalse(w.feed('x - Send Q#'))
        self.assertTrue(w.feed('x - Read OK 36'))

    def test_rejects_other_command(self):
        w = self.waiter()
        with self.assertRaises(RuntimeError):
            w.feed('x - guideOffset(): {"ra offset":20.0,"dec offset":0.0}')

    def test_rejects_early_stop(self):
        with self.assertRaises(RuntimeError):
            self.waiter().feed('x - Send Q#')

    def test_rounding_and_two_axis_movement(self):
        w = self.waiter()
        w.command = (19.86037344472111, -100.)
        w.allowed_directions = {'MW#', 'MN#'}
        w.seen_directions = set()
        w.feed('x - guideOffset(): {"ra offset":19.8603734447211,"dec offset":-100.0}')
        w.feed('x - Send MW#')
        w.feed('x - Send MN#')
        w.feed('x - Send Q#')
        self.assertTrue(w.feed('x - Read OK 36'))

    def test_duplicate_guide_is_still_rejected(self):
        w = self.waiter()
        line = 'x - guideOffset(): {"ra offset":0.0,"dec offset":-40.0}'
        w.feed(line)
        with self.assertRaises(RuntimeError):
            w.feed(line)

if __name__ == '__main__': unittest.main()
