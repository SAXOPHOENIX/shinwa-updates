#!/usr/bin/env python3
"""Validate, build, sign, and render a public Shinwa dictionary release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://saxophoenix.github.io/shinwa-updates"
EXPECTED_PUBLIC_KEY = "wqInep1D1G/TN4VWJhNM5pWlAReL+UtOyfgyfEk92O0="
MAX_FALSE_CORRECTION_RATE = 0.01
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SOURCE_COMMIT = re.compile(r"^[a-f0-9]{40}$")
SAFETY_TOKENS = ("左", "右", "両側", "陽性", "陰性", "認めず", "認めない", "なし", "ない", "あり", "ある")
GENERAL_NEGATIVES = (
    "右ではなく左の肺に陰影はありません。",
    "検査結果は陰性で、発熱もありません。",
    "薬を一日二回、一錠ずつ服用します。",
    "酸素を毎分二リットル投与しています。",
    "痛みはありますが、しびれはありません。",
)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: JSON object is required")
    return value


def load_dictionary(path: Path, key: str) -> dict[str, Any]:
    value = load_object(path)
    if value.get("schema_version") != 1 or value.get("locale") != "ja-JP":
        raise ValueError(f"{path.name}: schema_version=1 and locale=ja-JP are required")
    records = value.get(key)
    if not isinstance(records, dict):
        raise ValueError(f"{path.name}: {key} must be an object")
    return records


def dangerous_change(source: str, target: str) -> bool:
    number_pattern = r"\d+(?:\.\d+)?|[〇零一二三四五六七八九十百千万億兆]+"
    if re.findall(number_pattern, source) != re.findall(number_pattern, target):
        return True
    return any((token in source) != (token in target) for token in SAFETY_TOKENS)


def clean_records(records: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for raw_source, raw_record in records.items():
        if not isinstance(raw_record, dict):
            raise ValueError(f"{kind}: {raw_source!r} must contain an object")
        source = str(raw_source).strip()
        target = str(raw_record.get("target", "")).strip()
        if not source or not target:
            raise ValueError(f"{kind}: empty source or target is not allowed")
        if source == target:
            raise ValueError(f"{kind}: identical correction is not allowed: {source}")
        if len(source) > 100 or len(target) > 100 or CONTROL.search(source) or CONTROL.search(target):
            raise ValueError(f"{kind}: invalid characters or length: {source}")
        if kind != "hotwords" and dangerous_change(source, target):
            raise ValueError(f"{kind}: unsafe numeric, laterality, or polarity change: {source} -> {target}")
        if kind == "hotwords" and raw_record.get("negative_test_passed") is not True:
            continue
        if kind != "hotwords" and raw_record.get("negative_test_passed") is not True:
            raise ValueError(f"{kind}: negative test failed: {source}")
        cleaned.append({
            "source": source,
            "target": target,
            "reading": str(raw_record.get("reading", "")).strip()[:100],
            "category": str(raw_record.get("category", "")).strip()[:80],
            "department": str(raw_record.get("department", "")).strip()[:80],
            "confidence": round(float(raw_record.get("confidence", 0.0)), 4),
            "observations": max(0, int(raw_record.get("observations", 0))),
            "false_corrections": max(0, int(raw_record.get("false_corrections", 0))),
        })
    return sorted(cleaned, key=lambda item: item["source"])


def verify_negative_examples(automatic: list[dict[str, Any]]) -> None:
    for sentence in GENERAL_NEGATIVES:
        corrected = sentence
        for item in automatic:
            corrected = corrected.replace(item["source"], item["target"])
        if corrected != sentence:
            raise ValueError(f"general negative sentence was changed: {sentence}")


def false_correction_rate(automatic: list[dict[str, Any]]) -> float:
    observations = sum(max(1, item["observations"]) for item in automatic)
    failures = sum(item["false_corrections"] for item in automatic)
    return failures / max(observations, 1)


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def signing_public_key(private_key: Path) -> tuple[Path, str]:
    temporary = tempfile.NamedTemporaryFile(prefix="shinwa-public-", suffix=".der", delete=False)
    temporary.close()
    der_path = Path(temporary.name)
    run("openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER", "-out", str(der_path))
    raw = der_path.read_bytes()[-32:]
    return der_path, base64.b64encode(raw).decode("ascii")


def current_version(docs: Path) -> int:
    path = docs / "v1" / "dictionaries" / "generated_ja_manifest.json"
    if not path.exists():
        return 0
    manifest = load_object(path)
    version = manifest.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("existing manifest version is invalid")
    return version


def write_json_bytes(path: Path, payload: dict[str, Any]) -> bytes:
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def render_updates_page(
    docs: Path,
    *,
    version: int,
    published_at: datetime,
    source_commit: str,
    release: dict[str, Any],
    hotwords: list[dict[str, Any]],
    contextual: list[dict[str, Any]],
    automatic: list[dict[str, Any]],
    false_rate: float,
    evaluated_audio: int,
) -> None:
    improvements: list[str] = []
    if hotwords:
        improvements.append("短い医療用語を、より聞き取りやすくしました")
    if contextual:
        improvements.append("診療内容に合う医療用語を優先するよう改善しました")
    if automatic:
        improvements.append("安全確認済みの聞き間違いを自動で整えるよう改善しました")
    improvements.append("一般的な文章が医療用語へ誤って変わらないことを確認しました")
    items = "".join(f"<li>{html.escape(item)}</li>" for item in improvements)
    raw_accuracy = float(release.get("raw_accuracy", 0.0) or 0.0)
    corrected_accuracy = float(release.get("corrected_accuracy", raw_accuracy) or raw_accuracy)
    improvement = max(0.0, corrected_accuracy - raw_accuracy) * 100
    display_version = f"{published_at:%Y.%m}.{version}"
    content = f'''<!doctype html>
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
    <p class="release-date">公開日 {published_at:%Y年%m月%d日}</p>
    <section class="content-section"><h2>今回の改善</h2><ul class="improvements">{items}</ul></section>
    <section class="content-section"><h2>利用者が感じる変化</h2><p class="lead">医療用語をより自然に聞き取り、会話の流れに合う言葉を選びやすくなりました。</p></section>
    <section class="content-section"><h2>品質確認</h2><div class="quality-grid">
      <div class="quality-item"><span>評価した音声</span><strong>{evaluated_audio}件</strong></div>
      <div class="quality-item"><span>医療用語の認識改善</span><strong>{improvement:.1f}%</strong></div>
      <div class="quality-item"><span>誤補正率</span><strong>{false_rate * 100:.2f}%</strong></div>
      <div class="quality-item"><span>安全確認済み補正</span><strong>{len(automatic)}件</strong></div>
    </div></section>
    <section class="content-section"><details><summary>技術情報</summary><ul class="technical-list">
      <li>Whisperモデル: {html.escape(str(release.get('whisper_model', '未記録')))}</li>
      <li>試行数: {int(release.get('trials', 0) or 0)}回</li>
      <li>hotwords: {len(hotwords)}件</li>
      <li>文脈条件付き補正: {len(contextual)}件</li>
      <li>自動補正: {len(automatic)}件</li>
      <li>GitHubコミット: <code>{html.escape(source_commit)}</code></li>
      <li>manifestバージョン: {version}</li>
    </ul></details></section>
  </main>
  <footer class="site-footer"><div class="site-footer-inner">診和</div></footer>
</body>
</html>
'''
    target = docs / "updates" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def publish(source_root: Path, docs: Path, private_key: Path, source_commit: str) -> dict[str, Any]:
    if not SOURCE_COMMIT.fullmatch(source_commit):
        raise ValueError("source_commit must be a full 40-character commit SHA")
    data = source_root / "data"
    hotwords = clean_records(load_dictionary(data / "hotwords.json", "candidates"), "hotwords")
    contextual = clean_records(load_dictionary(data / "contextual_corrections.json", "corrections"), "contextual")
    automatic = clean_records(load_dictionary(data / "automatic_corrections.json", "corrections"), "automatic")
    release = load_object(data / "release_manifest.json")
    if release.get("schema_version") != 2:
        raise ValueError("release_manifest.json: schema_version=2 is required")
    verify_negative_examples(automatic)
    error_rate = false_correction_rate(automatic)
    if error_rate > MAX_FALSE_CORRECTION_RATE:
        raise ValueError(f"false correction rate {error_rate:.2%} exceeds {MAX_FALSE_CORRECTION_RATE:.2%}")

    previous = current_version(docs)
    version = previous + 1
    published_at = datetime.now(timezone.utc).replace(microsecond=0)
    dictionary_name = f"generated_ja_v{version}.json"
    dictionaries = docs / "v1" / "dictionaries"
    dictionary_payload = {
        "version": version,
        "locale": "ja-JP",
        "generated_by": "shinwa-speech-dictionary-lab",
        "source_commit": source_commit,
        "terms": [],
        "misrecognitions": {item["source"]: item["target"] for item in automatic},
        "hotwords": [
            {key: item[key] for key in ("target", "reading", "category") if item[key]}
            for item in hotwords
        ],
        "contextual_corrections": [
            {key: item[key] for key in ("source", "target", "reading", "category", "department") if item[key]}
            for item in contextual
        ],
        "automatic_corrections": {item["source"]: item["target"] for item in automatic},
    }
    dictionary_bytes = write_json_bytes(dictionaries / dictionary_name, dictionary_payload)
    manifest = {
        "schema_version": 1,
        "dictionary_kind": "generated",
        "version": version,
        "locale": "ja-JP",
        "download_url": f"{BASE_URL}/v1/dictionaries/{dictionary_name}",
        "sha256": hashlib.sha256(dictionary_bytes).hexdigest(),
        "signature_algorithm": "Ed25519",
        "signature_url": f"{BASE_URL}/v1/dictionaries/generated_ja_manifest.sig",
        "published_at": published_at.isoformat().replace("+00:00", "Z"),
        "mapping_count": len(automatic),
    }
    manifest_path = dictionaries / "generated_ja_manifest.json"
    write_json_bytes(manifest_path, manifest)

    public_der, public_key = signing_public_key(private_key)
    try:
        if public_key != EXPECTED_PUBLIC_KEY:
            raise ValueError("signing key does not match the public key fixed in Shinwa")
        signature = dictionaries / "generated_ja_manifest.sig"
        run("openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(private_key), "-in", str(manifest_path), "-out", str(signature))
        if signature.stat().st_size != 64:
            raise ValueError("Ed25519 signature must be exactly 64 raw bytes")
        run("openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", str(public_der), "-in", str(manifest_path), "-sigfile", str(signature))
    finally:
        public_der.unlink(missing_ok=True)

    cases = json.loads((source_root / "evaluation" / "fixed_cases.json").read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixed audio evaluation cases are required")
    render_updates_page(
        docs,
        version=version,
        published_at=published_at,
        source_commit=source_commit,
        release=release,
        hotwords=hotwords,
        contextual=contextual,
        automatic=automatic,
        false_rate=error_rate,
        evaluated_audio=len(cases),
    )
    (docs / ".nojekyll").touch()
    return {
        "version": version,
        "source_commit": source_commit,
        "hotwords": len(hotwords),
        "contextual_corrections": len(contextual),
        "automatic_corrections": len(automatic),
        "false_correction_rate": error_rate,
        "sha256": manifest["sha256"],
        "signature_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--docs", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = publish(args.source_root, args.docs, args.private_key, args.source_commit.lower())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
