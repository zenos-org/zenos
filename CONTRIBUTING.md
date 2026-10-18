# Contributing to ZENOS

Thank you for helping. A few rules keep the project trustworthy:

1. **No unverified security claims.** If a change makes something "secure", add or update the row in
   [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) and include a test that demonstrates it.
2. **English first.** Code, comments, UI text and docs are written in English; translations come after.
3. **Familiar UI.** Staff must be able to use ZENOS without training. Prefer the conventions people already know
   over new interaction patterns, and keep controls visible (no hover-only buttons).
4. **No single-vendor lock-in.** New dependencies need a reason, a license compatible with Apache-2.0 (or a clear
   note when they are not), and a look at the project's own stated limitations.
5. **Never commit secrets or personal data.** Use the files in `config/examples/` as templates and keep real values
   outside the repository.
6. **Design first.** UI changes start as a frame in the ZENOS Figma file; the code follows the frame.

Before sending a change:

```
python3 -W error::ResourceWarning -m unittest discover -s tests
packaging/check-secrets.sh
```

Changes to the root services (`system/sbin`) are tested on a clean Debian 13 install of the package, not only in
the development layout. See [docs/RELEASING.md](docs/RELEASING.md) for releases.

By contributing you agree that your contributions are licensed under the Apache License 2.0.
