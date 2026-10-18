# Security policy

ZENOS is a Developer Preview. Known gaps are listed in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md); you do not need
to report those, but proofs of concept that show how they can be exploited are welcome.

## Reporting a vulnerability

Please report privately through GitHub's "Report a vulnerability" (private security advisory) on this repository.
Do not open a public issue for an unreported vulnerability.

Include what you found, how to reproduce it, and what an attacker gains. We will acknowledge your report, keep you
informed, and credit you in the release notes unless you prefer otherwise.

## Scope

In scope: everything in this repository — sealing and key handling, approvals, the sentinel and lock screen, the
ledger, storage nodes, the messenger and relay, the browser shell and apps.
Out of scope: vulnerabilities in upstream projects (report those upstream), and attacks that require physical
access to a running machine.
