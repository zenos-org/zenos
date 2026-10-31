## What this change does and why

<!-- One or two sentences. -->

## Checks

- [ ] `python3 -W error::ResourceWarning -m unittest discover -s tests` passes
- [ ] `packaging/check-secrets.sh` passes
- [ ] If `formal/` changed: `cd formal && lake build` passes
- [ ] If something is described as more secure: the row in `docs/THREAT_MODEL.md` is updated and a test shows it
- [ ] No secrets or personal data (use `config/examples/` as templates)
- [ ] UI changes: link to the Figma frame

<!-- See CONTRIBUTING.md for the full rules. -->
