"""The PC's identity key inside a TPM (zident). Runs against a software TPM (swtpm) when it and tpm2-tools are
installed; skipped otherwise. Run: python3 -m unittest discover -s tests"""
import base64, json, os, shutil, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[0:0] = [str(REPO / "system" / "lib"), str(REPO / "system" / "sbin")]
import zident                                                      # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(shutil.which("swtpm") and shutil.which("tpm2_sign"), "swtpm and tpm2-tools are not installed")
class TpmIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="zenos-tpm-test-"))
        port = free_port()
        cls.tpm = subprocess.Popen(["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={cls.tmp}",
                                    "--server", f"type=tcp,port={port}", "--ctrl", f"type=tcp,port={port + 1}",
                                    "--flags", "not-need-init,startup-clear"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.env = os.environ.get("TPM2TOOLS_TCTI")
        os.environ["TPM2TOOLS_TCTI"] = f"swtpm:host=127.0.0.1,port={port}"
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        cls.saved = zident.CONF
        zident.CONF = cls.tmp / "identity.json"
        cls.ident = zident.setup_tpm(pcrs="7")

    @classmethod
    def tearDownClass(cls):
        zident.CONF = cls.saved
        if cls.env is None:
            os.environ.pop("TPM2TOOLS_TCTI", None)
        else:
            os.environ["TPM2TOOLS_TCTI"] = cls.env
        cls.tpm.terminate()
        cls.tpm.wait(timeout=10)

    def test_signs_and_is_selected(self):
        self.assertEqual(json.loads(zident.CONF.read_text())["kind"], "tpm")
        i = zident.load()
        self.assertEqual(i.kind, "tpm")
        m = b"batch digest"
        self.assertTrue(zident.verify(i.pub(), i.sign(m), m))
        self.assertFalse(zident.verify(i.pub(), i.sign(m), b"another"))
        zident.check_pub(i.pub())

    def test_audit_node_takes_tpm_signed_batches(self):
        import zenos_auditnode, zenos_auditship
        node = zenos_auditnode.Node(self.tmp / "audit")
        node.enroll("pc-tpm", base64.b64encode(self.ident.pub()).decode())
        b = zenos_auditship.sign(self.ident, {"machine": "pc-tpm", "chain": "guard", "from": 0, "records": [],
                                              "status": {"services": {"zenos-keyd": "active"}}})
        code, ans = node.accept(b)
        self.assertEqual(code, 200, ans)
        b["records"] = [{"forged": True}]
        self.assertEqual(node.accept(b)[0], 403)

    def test_key_service_takes_tpm_signed_requests(self):
        import zenos_keysvc, zkeysvc
        svc = zenos_keysvc.Service(self.tmp / "keys")
        svc.enroll("pc-tpm", base64.b64encode(self.ident.pub()).decode())
        req = {"op": "open", "machine": "pc-tpm", "t": int(time.time()), "nonce": zkeysvc.b64(os.urandom(16))}
        _, enrolled, sig_ok, fresh = svc.verify({"req": req, "sig": zkeysvc.b64(self.ident.sign(zkeysvc.canon(req)))})
        self.assertTrue(enrolled and sig_ok and fresh)
        req2 = dict(req, nonce=zkeysvc.b64(os.urandom(16)))
        other = zident.FileIdentity(self.tmp / "other.key")
        self.assertFalse(svc.verify({"req": req2, "sig": zkeysvc.b64(other.sign(zkeysvc.canon(req2)))})[2])

    def test_zz_another_boot_state_cannot_use_the_key(self):
        """PCR 7 changes (another Secure Boot state): the TPM refuses to sign"""
        subprocess.run(["tpm2_pcrextend", "7:sha256=" + "11" * 32], check=True, capture_output=True)
        with self.assertRaises(zident.Unavailable):
            zident.load().sign(b"x")

    def test_broken_configuration_is_not_a_fallback(self):
        saved = zident.CONF
        zident.CONF = self.tmp / "broken.json"
        zident.CONF.write_text("{oops")
        try:
            with self.assertRaises(zident.Unavailable):
                zident.load()
        finally:
            zident.CONF = saved


if __name__ == "__main__":
    unittest.main()
