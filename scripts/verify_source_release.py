#!/usr/bin/env python3
"""Verify signed Windows Release assets before any public file is changed."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path


EXPECTED_PUBLIC_KEY = "wqInep1D1G/TN4VWJhNM5pWlAReL+UtOyfgyfEk92O0="
REQUIRED = {"hotwords.json", "contextual_corrections.json", "automatic_corrections.json", "update_manifest.json"}


def verify(release_dir: Path) -> dict[str, object]:
    sums = release_dir / "SHA256SUMS"
    signature = release_dir / "SHA256SUMS.sig"
    public_key = release_dir / "update-public-key.pem"
    if not sums.exists() or not signature.exists() or not public_key.exists() or signature.stat().st_size != 64:
        raise ValueError("signed SHA256SUMS release assets are incomplete")
    der = subprocess.run(["openssl", "pkey", "-pubin", "-in", str(public_key), "-outform", "DER"], check=True, capture_output=True).stdout
    if base64.b64encode(der[-32:]).decode("ascii") != EXPECTED_PUBLIC_KEY:
        raise ValueError("release public key does not match Shinwa's fixed public key")
    subprocess.run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(public_key), "-in", str(sums), "-sigfile", str(signature)], check=True, capture_output=True)

    expected: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match:
            raise ValueError("SHA256SUMS contains an invalid line")
        expected[match.group(2)] = match.group(1)
    if not REQUIRED.issubset(expected):
        raise ValueError("SHA256SUMS does not cover every required JSON file")
    for name in REQUIRED:
        path = release_dir / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise ValueError(f"release SHA-256 mismatch: {name}")
        json.loads(path.read_bytes())

    manifest = json.loads((release_dir / "update_manifest.json").read_bytes())
    if manifest.get("legacy_included") is not False:
        raise ValueError("release contains legacy corrections")
    return {"signature_verified": True, "source_sha256": {name: expected[name] for name in sorted(REQUIRED)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.release_dir), ensure_ascii=False))

