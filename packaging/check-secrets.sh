#!/bin/bash
# Release gate: fail if the tracked files contain anything that looks like a secret or a real phone number.
#   packaging/check-secrets.sh            (run from anywhere inside the repository)
cd "$(git rev-parse --show-toplevel)"
fail=0
hit() { echo "!! $1"; echo "$2" | head -5; fail=1; }
files=$(git ls-files | grep -v -E '(^|/)(package-lock\.json|.*\.min\.js|.*\.(png|jpg|svg|wav|woff2?|ttf|otf|ico|deb|zip|pptx|docx|xlsx))$')
scan() { echo "$files" | tr '\n' '\0' | xargs -0 grep -I -n -E "$1" 2>/dev/null | grep -v -E "${2:-^$}"; }
r=$(scan '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----'); [ -n "$r" ] && hit "private key" "$r"
r=$(scan '(sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[abp]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{30,})'); [ -n "$r" ] && hit "API key" "$r"
# Japanese mobile numbers (070/080/090), with or without +81; the test numbers +81000000xxx and the
# placeholder 1234 5678 are allowed
r=$(scan '(\+81[ -]?[789]0[ -]?[0-9]{4}[ -]?[0-9]{4}|\b0[789]0[ -]?[0-9]{4}[ -]?[0-9]{4}\b)' 'check-secrets\.sh|1234[ -]?5678'); [ -n "$r" ] && hit "phone number" "$r"
r=$(scan '(LIVEKIT_API_SECRET|api_secret|secret:)[ :=]+["'"'"']?[A-Za-z0-9/+]{24,}' 'check-secrets\.sh'); [ -n "$r" ] && hit "call server secret" "$r"
r=$(git ls-files | grep -E '\.(key|pem|p12|pfx)$|(^|/)\.env$|keys\.env$|livekit\.yaml$'); [ -n "$r" ] && hit "key or env file tracked" "$r"
[ $fail = 0 ] && echo "no secrets found in $(echo "$files" | wc -l) tracked files"
exit $fail
