"""ZENOS file format, levels and approval requests: the part both the desktop and the root services rely on.

Kept in the root-owned library so that root services never import code from the desktop program directory.
"""
import hashlib, json

MAGIC = b"ZENOS1\n"
FOLDERS = {"Basic · L1": (1, 1), "Green · L2-L3": (2, 3), "Red · L4": (4, 4), "Black · L5": (5, 5)}
LABEL = {1: "Public", 2: "Confidentiality 2", 3: "Confidentiality 3",
         4: "Important Economic Security Information", 5: "Specially Designated Secret"}
# approvals a level needs
REQUIRED = {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}
CORE_KEYS = ("id", "kind", "requester", "file", "file_hash", "level", "reason", "created", "scope")


def request_core(r):
    return {k: r[k] for k in CORE_KEYS if k in r}


def request_digest(r):
    return hashlib.sha256(json.dumps(request_core(r), sort_keys=True, ensure_ascii=False).encode()).digest()
