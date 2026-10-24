"""Dead-man watcher: no false alarm from a torn read or a slow start; a silent sensor still alarms."""
import json, sys, tempfile, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "system" / "lib"))
sys.path.insert(0, str(ROOT / "system" / "sbin"))
import zenos_heartbeat as hb  # noqa: E402


class Watcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.saved = (hb.HB, hb.LEDGER, hb.TIMEOUT, hb.GRACE, hb.zalarm)
        hb.HB, hb.LEDGER = str(t / "sensor.hb"), str(t / "ledger.jsonl")
        hb.TIMEOUT, hb.GRACE, hb.zalarm = 1.0, 1.5, None

    def tearDown(self):
        hb.HB, hb.LEDGER, hb.TIMEOUT, hb.GRACE, hb.zalarm = self.saved
        self.tmp.cleanup()

    def events(self):
        p = Path(hb.LEDGER)
        return [json.loads(l)["event"] for l in p.read_text().splitlines()] if p.exists() else []

    def test_torn_reads_do_not_alarm(self):
        stop = threading.Event()

        def old_style_sensor():                 # rewrites the file in place: readers can catch it empty
            while not stop.is_set():
                with open(hb.HB, "w") as f:
                    f.flush(); time.sleep(0.05)  # empty for a moment
                    f.write(str(time.time()))
                time.sleep(0.1)
        th = threading.Thread(target=old_style_sensor); th.start()
        try:
            hb.watcher(3)
        finally:
            stop.set(); th.join()
        self.assertNotIn("sensor-silenced", self.events())

    def test_slow_start_is_not_silence(self):
        def late_sensor():
            time.sleep(1.0)                     # starts within the grace period
            for _ in range(8):
                hb.beat(); time.sleep(0.3)
        th = threading.Thread(target=late_sensor); th.start()
        hb.watcher(3); th.join()
        self.assertNotIn("sensor-silenced", self.events())

    def test_a_sensor_that_never_starts_alarms_after_the_grace(self):
        hb.watcher(3)
        self.assertIn("sensor-silenced", self.events())
        rec = [json.loads(l) for l in Path(hb.LEDGER).read_text().splitlines()][0]
        self.assertTrue(rec["never_started"])

    def test_a_sensor_that_stops_alarms(self):
        def dying_sensor():
            for _ in range(3):
                hb.beat(); time.sleep(0.3)
        th = threading.Thread(target=dying_sensor); th.start()
        hb.watcher(3.5); th.join()
        self.assertIn("sensor-silenced", self.events())


if __name__ == "__main__":
    unittest.main()
