# Formal verification of the ZENOS decisions

The decisions that decide whether classified data is released or leaves are written in Lean 4 (`formal/`) with
machine-checked proofs of what they guarantee. The services do not reimplement them: keyd, guardd, the apps, the
ledger check, the audit nodes, the pre-send check and the network sentinel run `zenos-decide`, the program built from
the same Lean definitions, and follow its answer (`system/lib/zdecide.py`). Anything unexpected from it (missing,
timeout, unreadable answer) is a refusal; for the network sentinel, a cut.

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

### Where content may go (`Flow.lean`)

One decision for every place a copy of a file's content can reach: level folders (Save As), level windows (paste),
the system clipboard, the printer, external AI, the government's AI, the ministry's AI. The apps (zenos_app,
zenos-webview) and keyd's clipboard ask it; the launcher's AI table is checked against it by a test.

| Theorem | Statement |
|---|---|
| `no_write_down` | Content of a level reaches only folders and windows of that level or higher (public content excepted). |
| `flow_within_cap` | No place ever holds more than its ceiling: clipboard L2, printer L4, external AI L2, government AI L3, whatever the configuration says. |
| `l3_stays_inside` | L3 and above never reach the system clipboard or an AI outside the government. |
| `l4_ministry_ai_only` | L4 and above reach no AI but the ministry's own. |
| `l5_stays` | Specially Designated Secrets (L5) are never printed and leave the L5 places only for the ministry's AI. |
| `carry_monotone` | Moving a copy hop by hop never lowers its level. |

### The tamper-evident ledger (`Ledger.lean`)

| Theorem | Statement |
|---|---|
| `chainCheck_ok` | The check accepts exactly the chains whose links and hashes hold. |
| `accept_extends` | An audit node's copy stays an intact chain and only grows: a batch is accepted only if it continues it. |
| `history_unique` | For any hash function without collisions, two histories that pass the check and end at the same hash are the same history. The audit nodes hold that hash, so an altered past cannot be shown to them. |

### What leaves the PC (`Egress.lean`)

| Theorem | Statement |
|---|---|
| `send_sound` | Nothing unsealed or tampered passes the pre-send check, and nothing over the size line without an approved transfer. |
| `egress_cut_iff` | The network sentinel cuts a destination exactly when it is not approved, not already cut, and the bytes sent to it within the window reach the threshold. |
| `egress_cut_stays` | A cut destination stays cut. |
| `prune_prune` | Keeping only the recent part of the window loses nothing, as long as the clock does not go backwards. |

### Officers' signatures (`Protocol.lean`)

Signatures are modelled as unforgeable and the digest as collision-free (hypotheses of the theorems, the standard
assumptions about Ed25519 and SHA-256).

| Theorem | Statement |
|---|---|
| `approve_ne_decline` | An approval (32-byte digest) can never be read as a decline (`"decline:"` + digest) or the reverse. |
| `counted_was_signed_for` | A signature that counts for a request was made for exactly that request: same id, same stop. |
| `release_counts_only_this_stop` | A stop is released only with a signature, by an enrolled officer other than the stopped user, over the request that names this stop: approvals cannot be replayed from another request or another stop. |

Levels need 0, 1, 1, 2, 3 approvals (L1–L5, `required`, the same table as `zformat.REQUIRED`; a test checks they
agree). A release needs more officers than opening the file did (at least 2), capped by the enrolled officers other
than the stopped user; with none, it cannot be met and the PC stays stopped.

### Sign-in with the phone (`Cred.lean`)

| Theorem | Statement |
|---|---|
| `cred_sound` | A saved password is released only to the page whose origin, as the browser verified it, is the one it was saved for, over verified TLS, within the time limit, after a phone registered to this person signed this very request with the person verified on the phone (counter moving forward), and the person picked the code the browser showed. |
| `cred_once` | Every request is answered at most once: once answered, approved or not, it is refused. An answer cannot be replayed, and a wrong code cannot be retried on the same request. |
| `ask_bounded` | However many requests a program sends, and however fast, at most `max` prompts reach the phone within any window. |

The passkey checks (signature with the registered key, the signed challenge is this request's digest, client data
origin and relying party of the registered phone page, user-verified flag, counter) are made by `zwebauthn.py` and
passed to the decision as facts. The entry's key comes from the phone's passkey (WebAuthn PRF) and reaches the vault
service encrypted to that request's one-time key; the PC stores only ciphertext.

## What is trusted, not proved

- Cryptography: Ed25519 signature checks with the officers' enrolled keys, SHA-256 digests, AES-GCM; for sign-in,
  the passkey signature (ES256 / EdDSA), the PRF of the phone's authenticator, ECDH P-256 and HKDF. The services
  check these and pass the results (`sig_ok`, `digest_ok`) to the decision.
- The facts the services read from root-owned files: the clearance file, the enrolled officers, the stop state, the
  clock.
- The glue: `zdecide.py`, the parts of the services that gather facts and carry out the answer (write the request
  file, freeze or thaw processes, cut a destination), the folder-level and CIDR lookups, and the readers in
  `formal/Main.lean`.
- The network sensor (eBPF/bpftrace) that reports each outbound send.
- Lean's compiler and runtime, the Linux kernel, Python.
- What the proofs do not speak about: the firewall rules themselves, ledger shipping, the trust agent and the
  messenger are tested, not proved. The signature model in `Protocol.lean` is symbolic (unforgeability and
  collision resistance are assumed); a computational proof of the cryptography is out of scope.

## Building and checking

```
cd formal && lake build          # checks every proof and builds .lake/build/bin/zenos-decide
python3 -m unittest tests/test_decide.py
```

`packaging/build-deb.sh` builds it the same way and installs the program as `/usr/lib/zenos/zenos-decide`.
Lean 4 v4.34.1 (`formal/lean-toolchain`); no other dependency.

## Credit

The idea of proving these decisions in Lean came from [Nyxis](https://github.com/NyxFoundation/nyxis) by Nyx
Foundation, which proves the authorization of a web backend. It builds on earlier work, among it Amazon's
[Cedar](https://github.com/cedar-policy/cedar-spec) policy language, whose authorizer is formalized and verified in
Lean, and the [seL4](https://sel4.systems/) verified kernel. ZENOS uses none of their code; the proofs in `formal/`
were written for ZENOS.
