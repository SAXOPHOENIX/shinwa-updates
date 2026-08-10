from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def module(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


publisher = module("publish_dictionary")
verifier = module("verify_release")


def make_release(root: Path) -> None:
    common = {"schema_version": 1, "locale": "ja-JP"}
    (root / "hotwords.json").write_text(json.dumps({**common, "candidates": {
        "イントウ痛": {"target": "咽頭痛", "reading": "いんとうつう", "recognized_text": "公開しない評価文", "voice": "test"}
    }}, ensure_ascii=False), encoding="utf-8")
    (root / "contextual_corrections.json").write_text(json.dumps({**common, "corrections": {
        "気管市全息": {"target": "気管支喘息", "context": "公開しない文脈", "department": "呼吸器内科"}
    }}, ensure_ascii=False), encoding="utf-8")
    (root / "automatic_corrections.json").write_text(json.dumps({**common, "corrections": {}}), encoding="utf-8")
    (root / "update_manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "version": "2026.08.09.1253",
        "generated_at": "2026-08-09T12:53:44+09:00",
        "legacy_included": False,
        "hotword_candidates": 1,
        "contextual_corrections": 1,
        "automatic_corrections": 0,
        "false_correction_rate": 0.0,
        "maximum_false_correction_rate": 0.01,
    }), encoding="utf-8")


def test_integer_version_conversion() -> None:
    assert publisher.integer_version("2026.08.09.1253") == 202608091253
    with pytest.raises(ValueError):
        publisher.integer_version("2026.08.09")


def test_sanitizes_transcripts_and_keeps_structures_separate(tmp_path: Path) -> None:
    make_release(tmp_path)
    hotwords, contextual, automatic = publisher.sanitize_release_json(tmp_path)
    serialized = json.dumps([hotwords, contextual, automatic], ensure_ascii=False)
    assert "recognized_text" not in serialized
    assert "voice" not in serialized
    assert "公開しない文脈" not in serialized
    assert len(hotwords["candidates"]) == 1
    assert len(contextual["corrections"]) == 1
    assert automatic["corrections"] == {}


def test_accepts_schema_two_and_preserves_safe_context_rules(tmp_path: Path) -> None:
    make_release(tmp_path)
    hotwords_path = tmp_path / "hotwords.json"
    hotwords = json.loads(hotwords_path.read_text())
    hotwords["schema_version"] = 2
    hotwords_path.write_text(json.dumps(hotwords, ensure_ascii=False))
    contextual_path = tmp_path / "contextual_corrections.json"
    contextual = json.loads(contextual_path.read_text())
    contextual["schema_version"] = 2
    contextual["corrections"]["気管市全息"].update({
        "context_any": ["喘鳴", "呼吸器"],
        "exclude_any": ["市役所"],
        "confidence": 0.98,
        "false_positive_test_passed": True,
        "recognized_text": "公開しない患者文",
    })
    contextual_path.write_text(json.dumps(contextual, ensure_ascii=False))

    _, public_contextual, _ = publisher.sanitize_release_json(tmp_path)

    rule = public_contextual["corrections"][0]
    assert rule["context_any"] == ["喘鳴", "呼吸器"]
    assert rule["exclude_any"] == ["市役所"]
    assert rule["confidence"] == 0.98
    assert rule["false_positive_test_passed"] is True
    assert "recognized_text" not in json.dumps(rule, ensure_ascii=False)


def test_builds_schema_two_manifest_with_compatible_dictionary(tmp_path: Path) -> None:
    release = tmp_path / "release"
    docs = tmp_path / "docs"
    release.mkdir()
    make_release(release)
    key = tmp_path / "key.pem"
    publisher.subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True)
    public_der, generated_key = publisher.public_key(key)
    public_der.unlink()
    original_publisher_key = publisher.EXPECTED_PUBLIC_KEY
    original_verifier_key = verifier.EXPECTED_PUBLIC_KEY
    publisher.EXPECTED_PUBLIC_KEY = generated_key
    verifier.EXPECTED_PUBLIC_KEY = generated_key
    try:
        result = publisher.publish(release, docs, key, "dictionary-update-v2026.08.09.1253", "a" * 40)
        manifest = json.loads((docs / "v1/dictionaries/generated_ja_manifest.json").read_text())
        combined = json.loads((docs / "v1/dictionaries/generated_ja_v202608091253.json").read_text())
        assert result["version"] == 202608091253
        assert manifest["schema_version"] == 2
        assert manifest["display_version"] == "2026.08.09.1253"
        assert combined["misrecognitions"] == combined["automatic_corrections"] == {}
        assert (docs / "v1/dictionaries/generated_ja_manifest.sig").stat().st_size == 64
        assert verifier.verify(docs)["signature_verified"] is True
    finally:
        publisher.EXPECTED_PUBLIC_KEY = original_publisher_key
        verifier.EXPECTED_PUBLIC_KEY = original_verifier_key


def test_rejects_non_increasing_version(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    manifest = docs / "v1/dictionaries/generated_ja_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version":202608091253}', encoding="utf-8")
    assert publisher.current_version(docs) == 202608091253
