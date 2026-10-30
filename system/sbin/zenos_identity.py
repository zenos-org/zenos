#!/usr/bin/env python3
"""The key this PC identifies itself with: show it, or move it into the TPM (system/lib/zident.py)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
import zident                                                    # noqa: E402

if __name__ == "__main__":
    zident.main()
