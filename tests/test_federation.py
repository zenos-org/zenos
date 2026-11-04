"""Organizations reaching each other and place: the proven decisions ("federate", "place" in zenos-decide,
formal/ZenosFormal/Federation.lean) answer as the relay and the device expect. The relays themselves are tested
end to end by tests/messenger_federation.js. Build first: cd formal && lake build.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/lib"))
import zdecide

BOTH = [{"by": "ministry", "ok": True}, {"by": "prefecture", "ok": True}]


def fed(**kw):
    r = {"op": "federate", "authorities": ["ministry", "prefecture"], "k": 2, "from": "ministry", "to": "city",
         "relay_sig_ok": True, "fresh": True, "kind": "message", "level": 3,
         "members": [{"org": "ministry", "max_level": 5, "publish_only": False, "sigs": BOTH},
                     {"org": "city", "max_level": 3, "publish_only": False, "sigs": BOTH},
                     {"org": "geoid", "max_level": 1, "publish_only": True, "sigs": BOTH}]}
    r.update(kw)
    return zdecide.ask(r)


def place(**kw):
    r = {"op": "place", "base_allow": True, "level": 4, "zone_required": False, "gps_inside": False,
         "proof_inside": False, "abroad": False, "close_abroad_from": 3, "emergency": False, "emergency_share": False}
    r.update(kw)
    return zdecide.ask(r)


class Federate(unittest.TestCase):
    def setUp(self):
        if not zdecide.PROGRAM:
            self.fail("zenos-decide is not built (cd formal && lake build)")

    def test_listed_within_level(self):
        self.assertEqual(fed(), {"allow": True, "reason": None})
        self.assertEqual(fed(level=4)["reason"], "level")

    def test_signatures(self):
        self.assertEqual(fed(relay_sig_ok=False)["reason"], "signature")
        self.assertEqual(fed(fresh=False)["reason"], "replay")
        one = [{"by": "ministry", "ok": True}, {"by": "ministry", "ok": True}, {"by": "prefecture", "ok": False}]
        m = [{"org": "ministry", "max_level": 5, "publish_only": False, "sigs": BOTH},
             {"org": "city", "max_level": 3, "publish_only": False, "sigs": one}]
        self.assertEqual(fed(members=m)["reason"], "unlisted")
        self.assertEqual(fed(k=1)["reason"], "unlisted")          # k below 2 never counts
        self.assertEqual(fed(authorities=["ministry"], k=2)["reason"], "unlisted")

    def test_publish_only(self):
        self.assertTrue(fed(**{"from": "geoid", "kind": "alert", "level": 1})["allow"])
        self.assertEqual(fed(**{"from": "geoid", "kind": "message", "level": 1})["reason"], "publish-only")
        self.assertEqual(fed(to="geoid", kind="keys", level=1)["reason"], "publish-only")

    def test_unreadable_is_refused(self):
        with self.assertRaises(zdecide.Refused):
            fed(kind="whatever")


class Place(unittest.TestCase):
    def setUp(self):
        if not zdecide.PROGRAM:
            self.fail("zenos-decide is not built (cd formal && lake build)")

    def test_abroad_closes_from_l3(self):
        self.assertEqual(place(abroad=True)["reason"], "abroad")
        self.assertTrue(place(abroad=True, level=2)["allow"])

    def test_zone_needs_both(self):
        self.assertEqual(place(zone_required=True, gps_inside=True)["reason"], "outside")
        self.assertEqual(place(zone_required=True, proof_inside=True)["reason"], "outside")
        self.assertTrue(place(zone_required=True, gps_inside=True, proof_inside=True)["allow"])

    def test_faked_location_gains_nothing(self):
        for z in (False, True):
            for base in (False, True):
                for e in (False, True):
                    a = place(zone_required=z, base_allow=base, emergency=e, emergency_share=True, gps_inside=False)
                    b = place(zone_required=z, base_allow=base, emergency=e, emergency_share=True, gps_inside=True)
                    self.assertEqual(a, b)

    def test_emergency_sharing(self):
        e = dict(base_allow=False, emergency_share=True, gps_inside=True, proof_inside=True)
        self.assertTrue(place(emergency=True, **e)["allow"])
        self.assertEqual(place(emergency=False, **e)["reason"], "clearance")


class DeviceGeometry(unittest.TestCase):
    def test_polygon_and_fix(self):
        import subprocess, json
        js = os.path.join(os.path.dirname(__file__), "../messenger/zgeo.js")
        out = subprocess.run(["node", "-e", f"""
const g = require({json.dumps(os.path.abspath(js))});
const sq = [[37.4, 139.9], [37.4, 140.0], [37.5, 140.0], [37.5, 139.9]], now = 1e12;
console.log(JSON.stringify([
  g.inPolygon([37.45, 139.95], sq), g.inPolygon([37.55, 139.95], sq),
  g.inArea(null, {{ polygons: [sq], codes: ["072028"] }}, "072028"),
  g.placeRequest({{ baseAllow: true, level: 4, zone: sq, fix: {{ lat: 37.45, lon: 139.95, t: now, accuracy: 30 }}, now }}).gps_inside,
  g.placeRequest({{ baseAllow: true, level: 4, zone: sq, fix: {{ lat: 37.45, lon: 139.95, t: now - 600e3, accuracy: 30 }}, now }}).gps_inside,
  g.placeRequest({{ baseAllow: true, level: 4, zone: sq, fix: {{ lat: 37.45, lon: 139.95, t: now, accuracy: 900 }}, now }}).gps_inside]));
"""], capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(out.stdout), [True, False, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
