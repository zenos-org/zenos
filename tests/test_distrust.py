import os, sys, ssl, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/lib"))
import zdistrust

PEMS = open(os.path.join(os.path.dirname(__file__), "fixtures/emudhra-compromised.pem")).read()


class Distrust(unittest.TestCase):
    def test_every_compromised_certificate_is_refused(self):
        ders = [ssl.PEM_cert_to_DER_cert(p.strip() + "\n-----END CERTIFICATE-----\n")
                for p in PEMS.split("-----END CERTIFICATE-----") if "BEGIN" in p]
        self.assertEqual(len(ders), 16)
        for d in ders:
            self.assertIn("eMudhra", zdistrust.blocked([d]) or "")

    def test_ordinary_root_passes(self):
        bundle = open("/etc/ssl/certs/ca-certificates.crt").read().split("-----END CERTIFICATE-----")[:20]
        ders = [ssl.PEM_cert_to_DER_cert(p.strip() + "\n-----END CERTIFICATE-----\n") for p in bundle if "BEGIN" in p]
        self.assertIsNone(zdistrust.blocked(ders))


if __name__ == "__main__":
    unittest.main()
