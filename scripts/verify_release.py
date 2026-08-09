#!/usr/bin/env python3
"""Verify the exact public manifest bytes, payload hash, and raw signature."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


EXPECTED_PUBLIC_KEY = "wqInep1D1G/TN4VWJhNM5pWlAReL+UtOyfgyfEk92O0="


def verify(docs: Path) -> dict[str, object]:
    dictionaries = docs / "v1" / "dictionaries"
    manifest_path = dictionaries / "generated_ja_manifest.json"
    signature_path = dictionaries / "generated_ja_manifest.sig"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    required = {
        "schema_version", "dictionary_kind", "version", "locale", "download_url",
        "sha256", "signature_algorithm", "signature_url", "published_at", "mapping_count",
    }
    if set(manifest) != required:
        raise ValueError("manifest fields do not match the public contract")
    if manifest["schema_version"] != 1 or manifest["dictionary_kind"] != "generated" or manifest["locale"] != "ja-JP":
        raise ValueError("manifest schema is invalid")
    if manifest["signature_algorithm"] != "Ed25519" or signature_path.stat().st_size != 64:
        raise ValueError("signature format is invalid")
    payload = dictionaries / Path(manifest["download_url"]).name
    actual_hash = hashlib.sha256(payload.read_bytes()).hexdigest()
    if actual_hash != manifest["sha256"]:
        raise ValueError("dictionary SHA-256 mismatch")
    dictionary = json.loads(payload.read_bytes())
    if dictionary.get("version") != manifest["version"] or dictionary.get("locale") != "ja-JP":
        raise ValueError("dictionary version or locale mismatch")
    if dictionary.get("misrecognitions") != dictionary.get("automatic_corrections"):
        raise ValueError("only automatic corrections may be unconditional")
    if any("legacy" in key.lower() for key in dictionary):
        raise ValueError("legacy data must not be public")

    public_der = b"0*0\x05\x06\x03+ep\x03!\x00" + base64.b64decode(EXPECTED_PUBLIC_KEY)
    with tempfile.NamedTemporaryFile(prefix="shinwa-public-", suffix=".der") as public_file:
        public_file.write(public_der)
        public_file.flush()
        subprocess.run([
            "openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
            "-inkey", public_file.name, "-in", str(manifest_path), "-sigfile", str(signature_path),
        ], check=True, capture_output=True)
    return {"version": manifest["version"], "sha256": actual_hash, "signature_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.docs), ensure_ascii=False))

