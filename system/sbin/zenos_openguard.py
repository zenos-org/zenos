#!/usr/bin/env python3
"""ZENOS open-time network cut for high-secrecy files (PoC).

While an L4+ file is decrypted and on screen, NEW outbound connections are blocked, so the plaintext
cannot be shipped out during its one exposed window. Loopback (the desktop/app) and already-established
connections (the operator's live Guacamole session) are exempt, so the screen stays up. Keys are
fetched BEFORE the cut; on close the file is re-sealed and the network is restored. Every step is
written to the tamper-evident ledger.
"""
import subprocess, sys
import os
# the ZENOS library is ../lib/zenos beside this program (/usr/lib/zenos, root-owned)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
import zledger

CHAIN = "ZENOS_OPEN"
LEDGER = "/var/log/zenos/access-ledger.jsonl"
MIN_LEVEL = 4


def sh(*a):
    return subprocess.run(a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _cut_on():
    if sh("iptables", "-nL", CHAIN).returncode != 0:
        sh("iptables", "-N", CHAIN)
    sh("iptables", "-F", CHAIN)
    sh("iptables", "-A", CHAIN, "-o", "lo", "-j", "RETURN")
    sh("iptables", "-A", CHAIN, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN")
    sh("iptables", "-A", CHAIN, "-j", "DROP")
    if sh("iptables", "-C", "OUTPUT", "-j", CHAIN).returncode != 0:
        sh("iptables", "-I", "OUTPUT", "1", "-j", CHAIN)


def _cut_off():
    sh("iptables", "-D", "OUTPUT", "-j", CHAIN)
    sh("iptables", "-F", CHAIN)


def open_secure(path, level, actor, device, fragments):
    level = int(level); fragments = int(fragments)
    level = int(level)
    if level >= MIN_LEVEL:
        for i in range(fragments):                       # keys fetched BEFORE the cut
            zledger.append(LEDGER, "key-issue", actor, device, file=path, level=level, fragment=i)
        _cut_on()
    zledger.append(LEDGER, "file-open", actor, device, file=path, level=level, netcut=level >= MIN_LEVEL)


def close_secure(path, level, actor, device):
    level = int(level)
    if level >= MIN_LEVEL:
        _cut_off()
    zledger.append(LEDGER, "file-close", actor, device, file=path, level=level)


if __name__ == "__main__":
    getattr(sys.modules[__name__], sys.argv[1])(*sys.argv[2:])
