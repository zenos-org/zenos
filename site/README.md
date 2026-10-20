# Project website

Static one-page site (`index.html`), designed in Figma first (file x0pQlpFnMH8BpNDARH7LlJ, frame 43:2).
Nothing here is published yet.

Before publishing:

1. Replace every `ORG` with the GitHub organization name.
2. Put a real screenshot of the running desktop at `site/desktop.png` (fictitious content only).
3. Add `site/CNAME` containing the domain (zenos-os.org).

Publishing with GitHub Pages: repository Settings → Pages → Source "GitHub Actions" or "Deploy from a branch",
folder `/site`. Custom domain: enter the domain there and tick "Enforce HTTPS".

DNS records at the registrar for an apex domain:

```
A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
CNAME www  ORG.github.io
```

Verify the domain for the organization (Organization settings → Pages → Add a domain) so nobody else can claim it.
