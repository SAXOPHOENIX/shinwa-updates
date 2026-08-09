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


def write_source(root: Path, automatic: dict | None = None) -> None:
    data = root / "data"
    evaluation = root / "evaluation"
    data.mkdir(parents=True)
    evaluation.mkdir(parents=True)
    common = {"schema_version": 1, "locale": "ja-JP"}
    (data / "hotwords.json").write_text(json.dumps({**common, "candidates": {
        "イントウ痛": {"target": "咽頭痛", "reading": "いんとうつう", "negative_test_passed": True}
    }}, ensure_ascii=False), encoding="utf-8")
    (data / "contextual_corrections.json").write_text(json.dumps({**common, "corrections": {
        "気管市全息": {"target": "気管支喘息", "negative_test_passed": True}
    }}, ensure_ascii=False), encoding="utf-8")
    (data / "automatic_corrections.json").write_text(json.dumps({**common, "corrections": automatic or {
        "急性情起動": {"target": "急性上気道炎", "observations": 5, "false_corrections": 0, "negative_test_passed": True}
    }}, ensure_ascii=False), encoding="utf-8")
    (data / "release_manifest.json").write_text(json.dumps({
        "schema_version": 2, "raw_accuracy": 0.8, "corrected_accuracy": 0.9,
        "whisper_model": "small", "trials": 5,
    }), encoding="utf-8")
    (evaluation / "fixed_cases.json").write_text('[{"audio":"test.wav","text":"test"}]', encoding="utf-8")


def test_builds_versioned_dictionary_and_raw_signature(tmp_path: Path) -> None:
    source = tmp_path / "source"
    docs = tmp_path / "docs"
    key = tmp_path / "key.pem"
    write_source(source)
    publisher.run("openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key))
    public_der, public_key = publisher.signing_public_key(key)
    public_der.unlink()
    original = publisher.EXPECTED_PUBLIC_KEY
    publisher.EXPECTED_PUBLIC_KEY = public_key
    verifier.EXPECTED_PUBLIC_KEY = public_key
    try:
        first = publisher.publish(source, docs, key, "a" * 40)
        second = publisher.publish(source, docs, key, "b" * 40)
        assert first["version"] == 1
        assert second["version"] == 2
        assert (docs / "v1/dictionaries/generated_ja_manifest.sig").stat().st_size == 64
        payload = json.loads((docs / "v1/dictionaries/generated_ja_v2.json").read_text())
        assert payload["misrecognitions"] == payload["automatic_corrections"]
        assert "legacy_candidates" not in payload
        assert verifier.verify(docs)["signature_verified"] is True
    finally:
        publisher.EXPECTED_PUBLIC_KEY = original


@pytest.mark.parametrize("source,target", [
    ("右肺炎", "左肺炎"),
    ("検査陰性", "検査陽性"),
    ("二錠", "三錠"),
    ("症状なし", "症状あり"),
])
def test_rejects_dangerous_automatic_changes(tmp_path: Path, source: str, target: str) -> None:
    root = tmp_path / "source"
    write_source(root, {source: {"target": target, "negative_test_passed": True}})
    with pytest.raises(ValueError, match="unsafe"):
        publisher.clean_records(
            publisher.load_dictionary(root / "data/automatic_corrections.json", "corrections"),
            "automatic",
        )


def test_rejects_empty_and_identical_mappings() -> None:
    with pytest.raises(ValueError, match="empty"):
        publisher.clean_records({"": {"target": "咽頭痛"}}, "automatic")
    with pytest.raises(ValueError, match="identical"):
        publisher.clean_records({"咽頭痛": {"target": "咽頭痛"}}, "automatic")

