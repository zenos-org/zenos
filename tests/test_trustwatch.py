"""trust agent pieces that need no network: OneCRL key format, signature check, route rating"""
import base64, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/sbin"))
import zdistrust
import zenos_trustwatch as T
from cryptography import x509
from cryptography.hazmat.primitives import serialization

FIX = open(os.path.join(os.path.dirname(__file__), "fixtures/emudhra-compromised.pem")).read()


class TrustWatch(unittest.TestCase):
    def test_issuer_serial_matches_onecrl_format(self):
        c = x509.load_pem_x509_certificates(FIX.encode())[0]
        der = c.public_bytes(serialization.Encoding.DER)
        iss, ser = zdistrust.issuer_serial(der).split(":")
        self.assertEqual(base64.b64decode(iss), c.issuer.public_bytes())
        self.assertEqual(int.from_bytes(base64.b64decode(ser), "big", signed=True), c.serial_number)

    def test_learned_list_is_enforced_without_restart(self):
        c = x509.load_pem_x509_certificates(open("/etc/ssl/certs/ca-certificates.crt", "rb").read())[5]
        der = c.public_bytes(serialization.Encoding.DER)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "learned.json")
            old = zdistrust.LISTS[1]
            zdistrust.LISTS[1] = p
            try:
                self.assertIsNone(zdistrust.why(der))
                json.dump({"issuer_serial": {zdistrust.issuer_serial(der): "test"}}, open(p, "w"))
                self.assertEqual(zdistrust.why(der), "test")
            finally:
                zdistrust.LISTS[1] = old

    def test_tampered_onecrl_is_rejected(self):
        d = {"metadata": {"signature": {"signature": base64.urlsafe_b64encode(b"\1" * 96).decode()}},
             "changes": [], "timestamp": 1}
        with self.assertRaises(Exception):
            T.verify_changeset(d, FIX.encode())   # chain does not end at Mozilla's root

    def test_root_that_cross_signed_a_compromised_key_is_found(self):
        bad = T.compromised_pems()
        self.assertEqual(len(bad), 16)
        # the AAA root that cross-signed the eMudhra intermediates is in Node's built-in list
        import subprocess, ssl
        out = subprocess.run(["node", "-p", "JSON.stringify(require('tls').rootCertificates)"],
                             capture_output=True, text=True, env={"PATH": os.environ["PATH"]}).stdout
        roots = T.certs_of([ssl.PEM_cert_to_DER_cert(p) for p in json.loads(out)])
        hits = {T.vouches(r, bad) for r in roots} - {None}
        self.assertTrue(any("EM DV TLS CA - G3B" in h for h in hits), hits)


if __name__ == "__main__":
    unittest.main()
