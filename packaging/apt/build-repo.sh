#!/bin/bash
# Build or update the signed ZENOS apt repository.
#   packaging/apt/build-repo.sh REPO_DIR SIGNING_KEY_ID build/zenos_*_amd64.deb
# REPO_DIR is then served as static files (any web server). PCs verify every update against the public key
# (zenos-archive-keyring.gpg, written next to the repository) before installing anything.
# The signing key belongs offline (a hardware token or an air-gapped machine); this script only needs gpg to
# reach it. Needs: apt-utils (apt-ftparchive), gnupg.
set -euo pipefail
[ $# -ge 3 ] || { sed -n 2,7p "$0"; exit 1; }
REPO=$1; KEY=$2; shift 2
SUITE=trixie
mkdir -p "$REPO/pool/main" "$REPO/dists/$SUITE/main/binary-amd64"
for d in "$@"; do cp -n "$d" "$REPO/pool/main/" || true; done
cd "$REPO"
apt-ftparchive packages pool/main > "dists/$SUITE/main/binary-amd64/Packages"
gzip -9kf "dists/$SUITE/main/binary-amd64/Packages"
apt-ftparchive \
  -o APT::FTPArchive::Release::Origin=ZENOS -o APT::FTPArchive::Release::Label=ZENOS \
  -o APT::FTPArchive::Release::Suite=$SUITE -o APT::FTPArchive::Release::Codename=$SUITE \
  -o APT::FTPArchive::Release::Architectures=amd64 -o APT::FTPArchive::Release::Components=main \
  -o APT::FTPArchive::Release::Description="ZENOS (Developer Preview)" \
  release "dists/$SUITE" > "dists/$SUITE/Release.tmp"
mv "dists/$SUITE/Release.tmp" "dists/$SUITE/Release"
gpg --batch --yes --local-user "$KEY" --digest-algo SHA512 --clearsign -o "dists/$SUITE/InRelease" "dists/$SUITE/Release"
gpg --batch --yes --local-user "$KEY" --digest-algo SHA512 -abs -o "dists/$SUITE/Release.gpg" "dists/$SUITE/Release"
gpg --batch --yes --export "$KEY" > zenos-archive-keyring.gpg
cat > zenos.sources <<EOF
Types: deb
URIs: https://REPLACE-WITH-YOUR-REPOSITORY-URL/
Suites: $SUITE
Components: main
Signed-By: /usr/share/keyrings/zenos-archive-keyring.gpg
EOF
echo "repository ready in $REPO ($(ls pool/main | wc -l) package file(s)); key fingerprint:"
gpg --batch --with-colons --fingerprint "$KEY" | awk -F: '/^fpr/{print $10; exit}'
