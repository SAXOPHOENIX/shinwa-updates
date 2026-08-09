#!/usr/bin/env python3
"""Verify the exact Pages manifest bytes, every public hash, and signature."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


EXPECTED_PUBLIC_KEY = "wqInep1D1G/TN4VWJhNM5pWlAReL+UtOyfgyfEk92O0="


def verify(docs: Path) -> dict[str, object]:
    root = docs / "v1/dictionaries"
    manifest_path = root / "generated_ja_manifest.json"
    signature = root / "generated_ja_manifest.sig"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("schema_version") != 2 or manifest.get("dictionary_kind") != "generated" or manifest.get("locale") != "ja-JP":
        raise ValueError("public manifest schema is invalid")
    if not isinstance(manifest.get("version"), int) or manifest["version"] < 1:
        raise ValueError("public manifest version must be a positive integer")
    if manifest.get("signature_algorithm") != "Ed25519" or signature.stat().st_size != 64:
        raise ValueError("public signature format is invalid")
    urls = [manifest.get("signature_url"), manifest.get("release_url"), manifest.get("release_notes_url"), manifest.get("download_url")]
    urls.extend(item.get("url") for item in manifest.get("files", {}).values())
    if any(urlparse(str(url)).scheme != "https" for url in urls):
        raise ValueError("every public URL must use HTTPS")
    for item in manifest["files"].values():
        path = root / Path(urlparse(item["url"]).path).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"public SHA-256 mismatch: {path.name}")
        payload = json.loads(path.read_bytes())
        if payload.get("locale") != "ja-JP" or any("legacy" in key.lower() for key in payload):
            raise ValueError(f"unsafe public JSON: {path.name}")
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        if any(term in serialized for term in ("recognized_text", "transcript", "voice", "patient_id", "患者id")):
            raise ValueError(f"diagnostic or transcript data is public: {path.name}")
    combined = root / Path(urlparse(manifest["download_url"]).path).name
    if hashlib.sha256(combined.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("combined compatibility dictionary SHA-256 mismatch")

    public_der = b"0*0\x05\x06\x03+ep\x03!\x00" + base64.b64decode(EXPECTED_PUBLIC_KEY)
    with tempfile.NamedTemporaryFile(prefix="shinwa-public-", suffix=".der") as public_file:
        public_file.write(public_der)
        public_file.flush()
        subprocess.run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", public_file.name, "-in", str(manifest_path), "-sigfile", str(signature)], check=True, capture_output=True)
    return {"version": manifest["version"], "display_version": manifest["display_version"], "signature_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.docs), ensure_ascii=False))

