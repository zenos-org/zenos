# Formal verification of the ZENOS decisions

The decisions that decide whether classified data is released are written in Lean 4 (`formal/`) with
machine-checked proofs of what they guarantee. The root services do not reimplement them: keyd and guardd run
`zenos-decide`, the program built from the same Lean definitions, and follow its answer
(`system/lib/zdecide.py`). Anything unexpected from it (missing, timeout, unreadable answer) is a refusal.

## What is proved

`formal/ZenosFormal/Proofs.lean`, checked by Lean's kernel on every build. `formal/ZenosFormal/Axioms.lean` fails the
build unless the theorems rest only on Lean's standard axioms (`propext`, `Quot.sound`): no `sorry`, no added axiom.

| Theorem | Statement |
|---|---|
| `open_sound` | keyd hands out a file's plaintext only if the PC is not stopped, the level is 1–5, and either the user's clearance covers the level or a grant does: for this user, this exact file (SHA-256), a level at least the file's, not expired, an access grant (not a release or plan), whose stored digest matches its signed contents, signed by at least the number of officers the level needs. |
| `grant_needs_officer` | Opening above one's clearance needs at least one enrolled officer, other than the user, whose signature verified. |
| `approvers_not_requester`, `approvers_nodup` | The requester's own approval never counts, and no officer counts twice. |
| `release_sound` | A stop is released only for a pending request signed by at least `required`, and at least one, distinct enrolled officers other than the stopped user. |
| `run_open_not_halted` | Over any sequence of anomalies, officers' answers, enforcement checks and open requests, every file keyd opened was opened while the PC was not stopped. |
| `run_release` | Over any such sequence, the PC goes from stopped to running only through a release check that held. |

Levels need 0, 1, 1, 2, 3 approvals (L1–L5, `required`, the same table as `zformat.REQUIRED`; a test checks they
agree). A release needs more officers than opening the file did (at least 2), capped by the enrolled officers other
than the stopped user; with none, it cannot be met and the PC stays stopped.

## What is trusted, not proved

- Cryptography: Ed25519 signature checks with the officers' enrolled keys, SHA-256 digests, AES-GCM. The services
  check these and pass the results (`sig_ok`, `digest_ok`) to the decision.
- The facts the services read from root-owned files: the clearance file, the enrolled officers, the stop state, the
  clock.
- The glue: `zdecide.py`, the parts of keyd and guardd that gather facts and carry out the answer (write the
  request file, freeze or thaw processes), and the JSON reader in `formal/Main.lean`.
- Lean's compiler and runtime, the Linux kernel, Python.
- What the proofs do not speak about: the other protections of ZENOS (network sentinel, firewall, ledger shipping,
  trust agent) are tested, not proved.

## Building and checking

```
cd formal && lake build          # checks every proof and builds .lake/build/bin/zenos-decide
python3 -m unittest tests/test_decide.py
```

`packaging/build-deb.sh` builds it the same way and installs the program as `/usr/lib/zenos/zenos-decide`.
Lean 4 v4.34.1 (`formal/lean-toolchain`); no other dependency.
