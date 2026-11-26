# ZENOS glossary

## Clearance

A clearance is the highest level a user may open without a grant, set by the administrator; the key agent hands out
plaintext only for a file at or below it, and records every refusal above it. See the file-sealing row and its
limitations in [what is real today](THREAT_MODEL.md#what-is-real-today-and-what-is-not).

## Conductor

The conductor runs an AI task on the person's PC, coordinates calls to model providers, and keeps the task data and token table locally. It is in 0.2.0; see [the conductor's parts](ORCHESTRATOR.md#the-parts) and the limitations in that document.

## Egress

Egress is what leaves the PC: the pre-send check evaluates files before sending, while the network sentinel checks outbound traffic against approved destinations and a byte threshold. See [what leaves the PC](FORMAL_VERIFICATION.md#what-leaves-the-pc-egresslean).

## Federation

Federation lets ZENOS Messages relays at different organizations exchange encrypted envelopes through a shared, signed member list. It is in 0.2.0; see [organizations reaching each other](FEDERATION.md#2-organizations-reaching-each-other-federation).

## Grant

A grant is an approval signed by officers that lets a request through: opening a file above one's clearance names that exact file, at a level the officers signed and not past its expiry, and a requester's own approval never counts. See [`open_sound`](FORMAL_VERIFICATION.md#what-is-proved) and [officers' signatures](FORMAL_VERIFICATION.md#officers-signatures-protocollean).

## Key service

The key service moves the master keys used to derive sealed-file keys off the PC and checks requests using its own records of users, grants and PC health. It is in 0.2.0 (the `zenos-grid` package); see [how the key service works](KEY_SERVICE.md#how-it-works).

## Ledger

A ledger is a hash-chained audit history; audit nodes accept batches only when they extend the chain the node already holds. See [the tamper-evident ledger](FORMAL_VERIFICATION.md#the-tamper-evident-ledger-ledgerlean) and its deployment limitations in the [threat model](THREAT_MODEL.md#what-is-real-today-and-what-is-not).

## Network sentinel

The network sentinel is a root service that sees every outbound connection, counts the bytes sent to each destination over a sliding window, and cuts any unapproved destination that reaches the threshold. See the network sentinel row and its limitations in [what is real today](THREAT_MODEL.md#what-is-real-today-and-what-is-not), and [what leaves the PC](FORMAL_VERIFICATION.md#what-leaves-the-pc-egresslean).

## Officer

An officer is an enrolled approver whose verified signature can authorize a request, such as access above a user's clearance or release of a stopped PC. The requester cannot count as their own approver; see [officers' signatures](FORMAL_VERIFICATION.md#officers-signatures-protocollean).

## Pre-send check

The pre-send check is a gate in front of the network sensor: it blocks anything unsealed, plaintext or tampered, and allows a file over the size line only with an approved transfer. See [`send_sound`](FORMAL_VERIFICATION.md#what-is-proved) and [what leaves the PC](FORMAL_VERIFICATION.md#what-leaves-the-pc-egresslean).

## Sealed file

A sealed file is encrypted and fragmented with a signed header; the key agent seals and opens it according to the user's clearance or an officer-approved grant. See the file-sealing row and its limitations in [what is real today](THREAT_MODEL.md#what-is-real-today-and-what-is-not).

## zenos-decide

`zenos-decide` is the decision program built from the Lean sources in `formal/`, which the key agent, the guard, the audit nodes, the pre-send check and the network sentinel run and follow; anything unexpected from it (missing, timeout, unreadable answer) is a refusal, and for the network sentinel, a cut. See [formal verification of the ZENOS decisions](FORMAL_VERIFICATION.md).
