"""ZENOS Images · Library and Studio (core/bin/zenos_studio.py)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core", "bin"))
import zenos_studio as S  # noqa: E402

FF = shutil.which("ffmpeg")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
def put(p, b):
    with open(p, "wb") as f:
        f.write(b)


def get(p):
    with open(p, "rb") as f:
        return f.read()


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.old = (S.HOME, S.META, S.OUT, S.POLICY)
        S.HOME = self.home
        S.META = os.path.join(self.home, ".config/zenos/studio.json")
        S.OUT = os.path.join(self.home, "Videos", "ZENOS Studio")
        S.POLICY = os.path.join(self.home, "policy.conf")
        self.l1 = os.path.join(self.home, "Desktop", "Basic · L1")
        self.l4 = os.path.join(self.home, "Desktop", "Red · L4")
        os.makedirs(self.l1)
        os.makedirs(self.l4)
        os.makedirs(os.path.join(self.home, "Music"))
        self.pic = os.path.join(self.l1, "harbor.png")
        put(self.pic, PNG)

    def tearDown(self):
        S.HOME, S.META, S.OUT, S.POLICY = self.old
        shutil.rmtree(self.home, ignore_errors=True)


class Library(Base):
    def test_lists_l1_media_and_never_higher_levels(self):
        put(os.path.join(self.home, "Music", "song.mp3"), b"x")
        put(os.path.join(self.l4, "secret.png"), PNG)
        put(os.path.join(self.l4, "memo.zen"), b"x")
        lib = S.library()
        names = [x["name"] for k in lib for x in lib[k]]
        self.assertIn("harbor.png", names)
        self.assertIn("song.mp3", names)
        self.assertNotIn("secret.png", names)
        self.assertNotIn("memo.zen", names)

    def test_meta_round_trip(self):
        m = S.meta_load()
        self.assertEqual(m["playlists"], [])
        m["pairs"]["/a.mp3"] = "/b.png"
        S.meta_save(m)
        self.assertEqual(S.meta_load()["pairs"], {"/a.mp3": "/b.png"})

    def test_sealed_and_higher_files_are_refused(self):
        p = os.path.join(self.l4, "secret.png")
        put(p, PNG)
        with self.assertRaises(ValueError):
            S._plain(p)
        z = os.path.join(self.l1, "x.zen")
        put(z, b"x")
        with self.assertRaises(ValueError):
            S._plain(z)


@unittest.skipUnless(FF, "ffmpeg is not installed")
class Media(Base):
    def setUp(self):
        super().setUp()
        self.wav = os.path.join(self.home, "Music", "tone.wav")
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", self.wav], check=True)
        jpg = os.path.join(self.l1, "pic.jpg")
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", jpg], check=True)
        self.jpg = jpg

    def dur(self, p):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                           capture_output=True, text=True)
        return float(r.stdout.strip())

    def test_peaks_and_length(self):
        r = S.peaks(self.wav, 100)
        self.assertAlmostEqual(r["duration"], 6.0, delta=0.05)
        self.assertGreaterEqual(len(r["peaks"]), 99)
        self.assertEqual(max(r["peaks"]), 1.0)

    def test_trim_with_fades(self):
        out = os.path.join(self.home, "Music", "cut.m4a")
        S.export_audio(self.wav, 1.0, 3.5, 0.5, 0.5, out)
        self.assertAlmostEqual(self.dur(out), 2.5, delta=0.1)

    def test_original_is_never_overwritten(self):
        with self.assertRaises(ValueError):
            S.export_audio(self.wav, 0, 1, 0, 0, self.wav)

    def test_picture_and_audio_make_one_video(self):
        out = os.path.join(self.home, "clip.mp4")
        S.export_video(self.wav, self.jpg, None, 2.0, 4.0, 0, 0.5, out)
        self.assertAlmostEqual(self.dur(out), 2.0, delta=0.15)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", out],
                           capture_output=True, text=True)
        self.assertIn("h264", r.stdout)
        self.assertIn("aac", r.stdout)


class Mock(BaseHTTPRequestHandler):
    mode = "direct"
    seen = []

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(ln))
        Mock.seen.append((self.headers.get("Authorization"), body))
        port = self.server.server_address[1]
        if Mock.mode == "direct":
            return self._send(200, "video/mp4", MP4)
        if Mock.mode == "poll":
            return self._send(200, "application/json", json.dumps({"status": "queued", "status_url": "http://127.0.0.1:%d/job/1" % port}).encode())
        return self._send(200, "application/json", json.dumps({"error": "quota exceeded"}).encode())

    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == "/job/1":
            return self._send(200, "application/json", json.dumps({"status": "succeeded", "video_url": "http://127.0.0.1:%d/v.mp4" % port}).encode())
        if self.path == "/v.mp4":
            return self._send(200, "video/mp4", MP4)
        self._send(404, "text/plain", b"no")


class AIMotion(Base):
    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/generate" % self.srv.server_address[1]
        Mock.seen = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_video_returned_directly_is_saved(self):
        Mock.mode = "direct"
        r = S.ai_video(self.pic, "slow pan", 5, self.url, "k-123", "m1")
        self.assertTrue(r["path"].startswith(S.OUT))
        self.assertEqual(get(r["path"]), MP4)
        auth, body = Mock.seen[0]
        self.assertEqual(auth, "Bearer k-123")
        self.assertEqual(body["prompt"], "slow pan")
        self.assertTrue(body["image"].startswith("data:image/png;base64,"))
        self.assertEqual(body["duration_seconds"], 5)

    def test_job_is_polled_until_the_video_is_ready(self):
        Mock.mode = "poll"
        r = S.ai_video(self.pic, "x", 4, self.url, "k", poll_every=0)
        self.assertEqual(get(r["path"]), MP4)

    def test_the_ai_error_is_shown(self):
        Mock.mode = "error"
        with self.assertRaisesRegex(RuntimeError, "quota exceeded"):
            S.ai_video(self.pic, "x", 4, self.url, "k")

    def test_only_l1_pictures_leave_the_pc(self):
        p = os.path.join(self.l4, "secret.png")
        put(p, PNG)
        with self.assertRaises((PermissionError, ValueError)):
            S.ai_video(p, "x", 4, self.url, "k")
        self.assertEqual(Mock.seen, [])

    def test_policy_can_turn_it_off(self):
        put(S.POLICY, b"studio_ai = off\n")
        with self.assertRaises(PermissionError):
            S.ai_video(self.pic, "x", 4, self.url, "k")
        self.assertEqual(Mock.seen, [])

    def test_plain_http_is_refused_except_on_this_pc(self):
        with self.assertRaises(ValueError):
            S.ai_video(self.pic, "x", 4, "http://example.com/gen", "k")


if __name__ == "__main__":
    unittest.main()
