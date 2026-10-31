#!/usr/bin/env python3
"""ZENOS conductor (docs/ORCHESTRATOR.md). Runs as the person, with the person's own API keys.

  zenos-conductor providers                       the providers configured, allowed, and their weights
  zenos-conductor preview "TASK" [CSV ...]        what would leave the PC for this task (nothing is sent)
  zenos-conductor run "TASK" [CSV ...]            masked work: the models write code on tokens, ZENOS runs it here,
                                                  results compared with each provider's weight
  zenos-conductor split TEXT.md TABLE.csv         a text and its table: the table to one provider (names masked),
                                                  the text to another (numbers masked)
Options: --outside  the material came from outside (web, mail, someone else): the task's destinations narrow.

Configuration: ~/.config/zenos/conductor.json (see /usr/lib/zenos/zorch.py). Nothing is configured by default, and
no API key ships with ZENOS.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
import zorch                                                     # noqa: E402


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    outside = "--outside" in a
    a = [x for x in a if x != "--outside"]
    conf = zorch.load_conf()
    cmd = a[0]
    if cmd == "providers":
        w = zorch.Weights()
        for p in conf["providers"]:
            ok = zorch.provider_ok(p)
            print(f"{p.get('name'):16} {p.get('kind'):18} {'allowed' if p.get('name') in conf['allowed'] else 'not allowed':12}"
                  f" {'' if ok else 'refused by ZENOS'}  weights: " +
                  ", ".join(f"{k}={w.get(k, p.get('name'))}" for k in ("table", "report")))
        if not conf["providers"]:
            print("No providers configured: add them to", zorch.CONF)
        return
    if cmd == "preview":
        m = zorch.Masker(conf["terms"])
        desc = [zorch.describe_csv(f, m, m.token("F", f"/work/in/f{i}.csv")) for i, f in enumerate(a[2:], 1)]
        mt = m.mask(a[1])
        print("Would leave the PC:\n")
        print(zorch.CODE_PROMPT.format(inputs="\n".join("- " + d for d in desc) or "- none", task=mt))
        lk = m.leaks(mt + "\n" + "\n".join(desc))
        print("\nReal values found in it:", ", ".join(lk) if lk else "none")
        return
    provs = zorch.load_providers(conf)
    if cmd == "run":
        if len(provs) < 2:
            sys.exit("At least two allowed providers are needed (one provider never decides alone).")
        r = zorch.masked_task(conf, a[1], a[2:], provs, tainted=outside)
        if r["accepted"]:
            print(r["result"])
            print(f"\n(accepted: {', '.join(r['by'])} agreed)", file=sys.stderr)
        else:
            print("No result was accepted: the providers did not agree.", file=sys.stderr)
            for p, out in r["results"].items():
                print(f"--- {p}\n{out if out is not None else '(failed)'}", file=sys.stderr)
            sys.exit(1)
        return
    if cmd == "split":
        if len(provs) < 2:
            sys.exit("At least two allowed providers are needed.")
        r = zorch.split_report(conf, open(a[1], encoding="utf-8").read(), a[2], provs)
        print(r["text"])
        print("\n---\n" + r["table_notes"])
        print(f"\n(table to {r['assignment']['table']}, text to {r['assignment']['text']})", file=sys.stderr)
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    try:
        main()
    except zorch.Refused as e:
        sys.exit(f"Refused: {e}")
