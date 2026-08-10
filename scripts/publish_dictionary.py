#!/usr/bin/env python3
"""Publish a verified Windows dictionary Release through stable Pages URLs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_URL = "https://saxophoenix.github.io/shinwa-updates"
SOURCE_REPOSITORY = "SAXOPHOENIX/shinwa-speech-dictionary-lab"
EXPECTED_PUBLIC_KEY = "wqInep1D1G/TN4VWJhNM5pWlAReL+UtOyfgyfEk92O0="
TAG_PATTERN = re.compile(r"^dictionary-update-v(\d{4}\.\d{2}\.\d{2}\.\d{4})$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: JSON object is required")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> bytes:
    value = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return value


def integer_version(display_version: str) -> int:
    parts = display_version.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        raise ValueError("release version must use YYYY.MM.DD.HHMM")
    return int("".join(parts))


def current_version(docs: Path) -> int:
    path = docs / "v1/dictionaries/generated_ja_manifest.json"
    if not path.exists():
        return 0
    value = load_object(path).get("version")
    if not isinstance(value, int) or value < 1:
        raise ValueError("existing public manifest version is invalid")
    return value


def public_key(private_key: Path) -> tuple[Path, str]:
    temporary = tempfile.NamedTemporaryFile(prefix="shinwa-public-", suffix=".der", delete=False)
    temporary.close()
    der = Path(temporary.name)
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER", "-out", str(der)],
        check=True,
        capture_output=True,
    )
    return der, base64.b64encode(der.read_bytes()[-32:]).decode("ascii")


def safe_record(source: str, record: dict[str, Any], *, contextual: bool) -> dict[str, Any]:
    target = str(record.get("target", "")).strip()
    source = source.strip()
    if not source or not target or source == target:
        raise ValueError("public correction contains an empty or identical mapping")
    allowed = ("source", "target", "reading", "category", "department") if contextual else ("target", "reading", "category")
    values = {
        "source": source,
        "target": target,
        "reading": str(record.get("reading", "")).strip()[:100],
        "category": str(record.get("category", "")).strip()[:80],
        "department": str(record.get("department", "")).strip()[:80],
    }
    result = {key: values[key] for key in allowed if values[key]}
    if contextual:
        for key in (
            "context_any",
            "prefix_any",
            "suffix_any",
            "exclude_any",
            "required_medical_terms",
            "departments",
        ):
            raw = record.get(key, [])
            if isinstance(raw, list):
                cleaned = list(
                    dict.fromkeys(
                        str(value).strip()[:100]
                        for value in raw
                        if str(value).strip()
                    )
                )[:30]
                if cleaned:
                    result[key] = cleaned
        confidence = record.get("confidence")
        if isinstance(confidence, (int, float)):
            result["confidence"] = max(0.0, min(float(confidence), 1.0))
        result["false_positive_test_passed"] = (
            record.get("false_positive_test_passed") is True
        )
    return result


def sanitize_release_json(release_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    hotwords = load_object(release_dir / "hotwords.json")
    contextual = load_object(release_dir / "contextual_corrections.json")
    automatic = load_object(release_dir / "automatic_corrections.json")
    for name, payload, key in (
        ("hotwords.json", hotwords, "candidates"),
        ("contextual_corrections.json", contextual, "corrections"),
        ("automatic_corrections.json", automatic, "corrections"),
    ):
        if payload.get("schema_version") not in (1, 2) or payload.get("locale") != "ja-JP" or not isinstance(payload.get(key), dict):
            raise ValueError(f"{name}: schema_version 1 or 2, locale=ja-JP, and an object payload are required")

    public_hotwords = {
        "schema_version": 1,
        "locale": "ja-JP",
        "candidates": [safe_record(str(source), record, contextual=False) for source, record in sorted(hotwords["candidates"].items())],
    }
    public_contextual = {
        "schema_version": 1,
        "locale": "ja-JP",
        "corrections": [safe_record(str(source), record, contextual=True) for source, record in sorted(contextual["corrections"].items())],
    }
    public_automatic = {
        "schema_version": 1,
        "locale": "ja-JP",
        "corrections": {
            str(source).strip(): str(record.get("target", "")).strip()
            for source, record in sorted(automatic["corrections"].items())
        },
    }
    for source, target in public_automatic["corrections"].items():
        if not source or not target or source == target:
            raise ValueError("automatic correction contains an empty or identical mapping")
    return public_hotwords, public_contextual, public_automatic


def render_updates(docs: Path, manifest: dict[str, Any]) -> None:
    metrics = manifest["metrics"]
    display_version = manifest["display_version"]
    published = datetime.fromisoformat(manifest["published_at"].replace("Z", "+00:00"))
    improvements = [
        "短い医療用語の聞き取り精度を改善しました",
        "診療内容に合う医療用語を優先するよう改善しました",
        "一般的な言葉が医療用語へ誤変換されないことを確認しました",
    ]
    items = "".join(f"<li>{html.escape(item)}</li>" for item in improvements)
    page = f'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="診和 {html.escape(display_version)} の改善内容と品質確認結果です。">
  <title>診和 アップデート {html.escape(display_version)}</title>
  <link rel="stylesheet" href="../assets/site.css">
</head>
<body>
  <header class="site-header"><div class="site-header-inner"><a class="brand" href="../">診和</a><nav><a href="./">更新履歴</a></nav></div></header>
  <main>
    <p class="eyebrow">診和 アップデート</p>
    <h1>{html.escape(display_version)}</h1>
    <p class="release-date">公開日 {published:%Y年%m月%d日}</p>
    <section class="content-section"><h2>今回の改善</h2><ul class="improvements">{items}</ul></section>
    <section class="content-section"><h2>利用者が感じる変化</h2><p class="lead">短い医療用語を捉えやすくし、診療内容に合う言葉を選びやすくなりました。</p></section>
    <section class="content-section"><h2>品質確認</h2><div class="quality-grid">
      <div class="quality-item"><span>認識支援候補</span><strong>{metrics['hotword_candidates']}件</strong></div>
      <div class="quality-item"><span>文脈を確認する補正</span><strong>{metrics['contextual_corrections']}件</strong></div>
      <div class="quality-item"><span>安全確認済み自動補正</span><strong>{metrics['automatic_corrections']}件</strong></div>
      <div class="quality-item"><span>評価上の誤補正率</span><strong>{float(metrics['false_correction_rate']) * 100:.2f}%</strong></div>
    </div></section>
    <section class="content-section"><details><summary>技術情報</summary><ul class="technical-list">
      <li>配信元: {html.escape(manifest['source_repository'])}</li>
      <li>GitHubコミット: <code>{html.escape(manifest['source_commit'])}</code></li>
      <li>リリース: <a href="{html.escape(manifest['release_url'])}">{html.escape(manifest['source_tag'])}</a></li>
      <li>manifestバージョン: {manifest['version']}</li>
    </ul></details></section>
  </main>
  <footer class="site-footer"><div class="site-footer-inner">診和</div></footer>
</body>
</html>
'''
    target = docs / "updates/index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")


def publish(release_dir: Path, docs: Path, private_key: Path, source_tag: str, source_commit: str) -> dict[str, Any]:
    match = TAG_PATTERN.fullmatch(source_tag)
    if not match or not COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("a fixed dictionary release tag and full commit SHA are required")
    display_version = match.group(1)
    version = integer_version(display_version)
    if version <= current_version(docs):
        raise ValueError("release version must increase monotonically")

    release_manifest = load_object(release_dir / "update_manifest.json")
    if release_manifest.get("schema_version") != 1 or release_manifest.get("version") != display_version:
        raise ValueError("release tag and update_manifest version do not match")
    if release_manifest.get("legacy_included") is not False:
        raise ValueError("legacy corrections must not be published")
    false_rate = float(release_manifest.get("false_correction_rate", 1.0))
    maximum_rate = float(release_manifest.get("maximum_false_correction_rate", 0.01))
    if false_rate > maximum_rate or maximum_rate > 0.01:
        raise ValueError("false correction rate exceeds the publication standard")

    hotwords, contextual, automatic = sanitize_release_json(release_dir)
    dictionaries = docs / "v1/dictionaries"
    public_files = {
        "hotwords": ("hotwords.json", hotwords),
        "contextual_corrections": ("contextual_corrections.json", contextual),
        "automatic_corrections": ("automatic_corrections.json", automatic),
    }
    file_manifest: dict[str, dict[str, str]] = {}
    for key, (name, payload) in public_files.items():
        content = write_json(dictionaries / name, payload)
        file_manifest[key] = {
            "url": f"{BASE_URL}/v1/dictionaries/{name}",
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    combined_name = f"generated_ja_v{version}.json"
    combined_payload = {
        "version": version,
        "locale": "ja-JP",
        "generated_by": "shinwa-speech-dictionary-lab",
        "source_commit": source_commit,
        "terms": [],
        "misrecognitions": automatic["corrections"],
        "hotwords": hotwords["candidates"],
        "contextual_corrections": contextual["corrections"],
        "automatic_corrections": automatic["corrections"],
    }
    combined = write_json(dictionaries / combined_name, combined_payload)
    published_at = str(release_manifest.get("generated_at", ""))
    datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    manifest = {
        "schema_version": 2,
        "dictionary_kind": "generated",
        "version": version,
        "display_version": display_version,
        "locale": "ja-JP",
        "published_at": published_at,
        "source_repository": SOURCE_REPOSITORY,
        "source_tag": source_tag,
        "source_commit": source_commit,
        "release_url": f"https://github.com/{SOURCE_REPOSITORY}/releases/tag/{source_tag}",
        "signature_algorithm": "Ed25519",
        "signature_url": f"{BASE_URL}/v1/dictionaries/generated_ja_manifest.sig",
        "files": file_manifest,
        "metrics": {
            "hotword_candidates": int(release_manifest.get("hotword_candidates", len(hotwords["candidates"]))),
            "contextual_corrections": int(release_manifest.get("contextual_corrections", len(contextual["corrections"]))),
            "automatic_corrections": int(release_manifest.get("automatic_corrections", len(automatic["corrections"]))),
            "false_correction_rate": false_rate,
        },
        "release_notes_url": f"{BASE_URL}/updates/",
        "download_url": f"{BASE_URL}/v1/dictionaries/{combined_name}",
        "sha256": hashlib.sha256(combined).hexdigest(),
        "mapping_count": len(automatic["corrections"]),
    }
    manifest_path = dictionaries / "generated_ja_manifest.json"
    write_json(manifest_path, manifest)

    public_der, key_base64 = public_key(private_key)
    try:
        if key_base64 != EXPECTED_PUBLIC_KEY:
            raise ValueError("site signing key does not match Shinwa's fixed public key")
        signature = dictionaries / "generated_ja_manifest.sig"
        subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(private_key), "-in", str(manifest_path), "-out", str(signature)], check=True, capture_output=True)
        if signature.stat().st_size != 64:
            raise ValueError("manifest signature must be 64 raw bytes")
        subprocess.run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", str(public_der), "-in", str(manifest_path), "-sigfile", str(signature)], check=True, capture_output=True)
    finally:
        public_der.unlink(missing_ok=True)

    render_updates(docs, manifest)
    (docs / ".nojekyll").touch()
    return {"version": version, "display_version": display_version, "files": file_manifest, "signature_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--docs", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.release_dir, args.docs, args.private_key, args.source_tag, args.source_commit.lower()), ensure_ascii=False))
