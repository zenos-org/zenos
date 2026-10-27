# Launch checklist

Checked 2026-10-27. Sources are the primary pages linked; "unconfirmed" means no primary source was reached.

## Name and accounts (decide first)

- GitHub organization:  (decided 2026-10-27;  is taken by a dormant 2019 hobby OS).
  `zenosos` returned 404 on 2026-10-27 (probably free; confirmed only when the organization is created).
- Other projects called ZenOS/zenOS exist (github.com/zenos-project, codeberg.org/Kripiron/ZenOS, an itch.io zenOS).
  Trademark "ZEN OS" filed in Australia, classes 9 and 42 (IP Australia 2674430). A class 9/42 check in Japan
  (J-PlatPat), the EU (EUIPO) and the US (USPTO) is still to be done by hand.
- Domains not registered on 2026-10-27 (registry RDAP): zenos-os.org, zenos-os.com, zenos-os.dev, zenosos.org, getzenos.org.

## Hosting (costs need approval)

| Part | Choice | Cost |
|---|---|---|
| Domain | Cloudflare Registrar (at-cost) | one .org fee a year (price on Cloudflare's page at checkout) |
| Website (`site/`) | Cloudflare Pages | free |
| Feedback board (`feedback/`) | Cloudflare Workers + D1 (free plan: 100,000 requests/day, 5 GB) | free |
| Mail on the domain (for the GitHub account) | Cloudflare Email Routing (receive and forward only) | free |
| Sign in | GitHub OAuth app | free |
| AI review every 4 hours | a scheduled task in the existing Claude plan, through the reviewer endpoints | no extra cost |

Order: register the domain → Email Routing (address → personal inbox) → create the GitHub organization with that
address → push the repository → Pages for `site/` → Worker + D1 for `feedback/` (feedback/README.md) → DNS.

## Filings

- United States (EAR): publicly available source code with only standard cryptography is not subject to the EAR,
  and since 2021 no e-mail notification is needed unless the cryptography is non-standard (15 CFR 742.15(b);
  86 FR 16482). ZENOS uses ECDH P-256, AES-GCM, Ed25519, HKDF, WebAuthn and LUKS2, all standard: nothing to file.
- Japan (外為法): providing a program whose source code is published is exempt as publicly known technology
  (貿易外省令 9条2項9号; METI Q&A). Non-public builds or support for a specific foreign party need a 該非判定 first.
- Debian: do not use "Debian" in product or domain names; "based on Debian" is allowed. The site footer says ZENOS
  is not affiliated with Debian or KDE. Publish the source of every binary package shipped (GPL): the ISO's source
  packages go to the release next to the ISO.
- Lean 4 is Apache-2.0.

## At launch

- SECURITY.md and GitHub private vulnerability reporting on (GitHub issues CVEs for advisories; no own CNA needed).
- `site/.well-known/security.txt` (RFC 9116); renew `Expires` before 2027-10-01.
- OpenSSF Best Practices badge (self-assessment at bestpractices.dev) in the first weeks.
- Later: DistroWatch after a stable release (it lists no alpha/beta), Debian derivatives census, Software Heritage.

## Telling engineers (first two weeks)

1. Day 0: site and repository public, ISO on the release, security policy on. Post on X and Mastodon.
2. Day 1 (Tue–Thu, US morning): Show HN. Only something people can try now; authors answer all day; never ask for
   votes. First comment: why it exists, the threat model, what the Lean proofs cover and what they do not.
3. Day 1–2: plain-text note to LWN (lwn@lwn.net) and Phoronix (news@phoronix.com).
4. Day 2–3: technical articles: Zenn or Qiita in Japanese (technical content, product mention only in a footer),
   an English deep-dive on the site or dev.to.
5. Day 3–5: r/linux and r/opensource after reading each subreddit's rules.
6. FOSDEM 2027 (Brussels, 30–31 Jan): stand applications close 31 Oct 2026 23:59 UTC; main track talks close
   16 Nov 2026 (fosdem.org/submit); Distributions and Security devroom calls follow.
7. Week 2: fix the first reports, point release, OpenSSF badge.

Wording: plain facts; say "Developer Preview" and what is not done. No claims of being secure before an audit.
