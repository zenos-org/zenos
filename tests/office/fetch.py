#!/usr/bin/env python3
"""Download the public files listed in corpus.json (each from the government or municipal page it was published
on) into a folder, and check each file's SHA-256. A file that changed or disappeared at its source is reported and
skipped, not replaced.  fetch.py OUT_DIR"""
import hashlib, json, os, sys, time, urllib.request
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
man = json.loads((Path(__file__).parent / "corpus.json").read_text())
UA = {"User-Agent": "ZENOS-compat-tests/0.1 (+https://zenos-os.org; hello@zenos-os.org)"}
bad = 0
for m in man:
    p = out / m["file"]
    if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == m["sha256"]:
        continue
    try:
        with urllib.request.urlopen(urllib.request.Request(m["url"], headers=UA), timeout=60) as r:
            b = r.read()
    except Exception as e:
        print("unavailable:", m["url"], e); bad += 1; continue
    if hashlib.sha256(b).hexdigest() != m["sha256"]:
        print("changed at the source, skipped:", m["url"]); bad += 1; continue
    p.write_bytes(b)
    time.sleep(0.5)
print(f"{len(man) - bad} of {len(man)} files ready in {out}")
