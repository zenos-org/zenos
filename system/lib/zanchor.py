#!/usr/bin/env python3
"""ZENOS two-tier ledger (PoC): many local edits, few consortium anchors.

Local tier  = the fine-grained hash chain of edits (zledger), kept/replicated on local grid nodes.
Consortium  = only the critical events plus, periodically, ONE Merkle-root anchor over the local batch.
The anchor is the trust root: recomputing the batch's root and comparing it to the anchored value detects
any local rewrite. Idempotent (re-anchoring the same batch yields the same root). This is the L2->L1 /
CloudTrail-digest pattern.
"""
import hashlib, json, os, sys
sys.path.insert(0, "/usr/local/lib/zenos")
import zledger


def _hashes(path):
    try:
        return [json.loads(l)["hash"] for l in open(path, encoding="utf-8").read().splitlines() if l.strip()]
    except FileNotFoundError:
        return []


def merkle_root(leaves):
    if not leaves:
        return "0" * 64
    layer = [bytes.fromhex(h) for h in leaves]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [hashlib.sha256(layer[i] + layer[i + 1]).digest() for i in range(0, len(layer), 2)]
    return layer[0].hex()


def _state(path):
    sp = path + ".anchor-state"
    try:
        return int(open(sp).read().strip())
    except Exception:
        return 0


def anchor(local_path, consortium_path, actor, device):
    """Anchor every local edit not yet anchored. Returns the anchor record hash, or None if nothing new."""
    leaves = _hashes(local_path)
    frm = _state(local_path)
    if len(leaves) <= frm:
        return None
    batch = leaves[frm:]
    root = merkle_root(batch)
    h = zledger.append(consortium_path, "edit-anchor", actor, device,
                       root=root, count=len(batch), from_idx=frm, to_idx=len(leaves),
                       from_hash=batch[0], to_hash=batch[-1])
    open(local_path + ".anchor-state", "w").write(str(len(leaves)))
    return h


def verify_anchor(local_path, consortium_path):
    """Recompute each anchored batch's root from the local chain; flag any mismatch (local tampering)."""
    leaves = _hashes(local_path)
    anchors = [json.loads(l) for l in open(consortium_path, encoding="utf-8").read().splitlines()
               if l.strip() and json.loads(l).get("event") == "edit-anchor"]
    problems = []
    for a in anchors:
        got = merkle_root(leaves[a["from_idx"]:a["to_idx"]])
        if got != a["root"]:
            problems.append({"range": [a["from_idx"], a["to_idx"]], "anchored": a["root"][:16], "recomputed": got[:16]})
    return (not problems), problems
