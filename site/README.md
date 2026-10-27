# Project website

Static one-page site (`index.html`, `img/`), built from the Figma frame "Website v2 — zenos-os.org"
(file x0pQlpFnMH8BpNDARH7LlJ, node 64:2). The Figma file is the source of the design.

No build step: any static host serves this folder. `CNAME` holds the domain for hosts that read it.
Links assume the GitHub organization ; change them in one place with
`sed -i 's#github.com/zenos-org#github.com/NEWORG#g' site/index.html` if the name differs.
