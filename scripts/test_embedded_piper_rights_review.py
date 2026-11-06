#!/usr/bin/env python3
"""Fail closed on experimental Piper distribution approvals.

This checks source-claimed licences and quarantine separation; it does NOT
verify speaker identity, publicity rights, offline synthesis, or human listening.
"""
import json
from pathlib import Path
from datetime import date

approved = json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text(encoding="utf-8"))
quarantine = json.loads(Path("Ghostline/Resources/quarantined-piper-candidates.json").read_text(encoding="utf-8"))
assert approved["schema_version"] == quarantine["schema_version"] == 1
assert approved["source_revision"] == quarantine["source_revision"]
assert approved["verified_identity_count"] == 0
assert approved["device_verified_audio_count"] == 0
assert approved["distribution_scope"] == "experimental unsigned IPA artifact only; not a public release"
active_ids = {p["id"] for p in approved["models"]}
held_ids = {p["id"] for p in quarantine["models"]}
assert active_ids and len(active_ids) == len(approved["models"])
assert len(held_ids) == len(quarantine["models"])
assert not active_ids.intersection(held_ids), "Quarantined model must not be bundled"
for item in quarantine["models"]:
    rights = item["rights_review"]
    assert rights["decision"] == "HOLD_SOURCE_PROVENANCE_RECONCILIATION"
    assert rights["not_for_distribution"] is True
    assert rights["identity_permissions_independently_verified"] is False
    assert rights["model_card_url"] == item["model_card_url"]
for item in approved["models"]:
    review = item["rights_review"]
    assert review["decision"] == "SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY", item["id"]
    assert date.fromisoformat(review["reviewed_at"]) <= date.today()
    assert review["model_card_url"] == item["model_card_url"]
    assert review["model_card_url"].startswith("https://huggingface.co/rhasspy/piper-voices/blob/")
    assert review["dataset_evidence_url"].startswith("https://")
    assert review["identity_permissions_independently_verified"] is False
    assert review["device_generation_verified"] is False
    assert item["claimed_real_person_identity"] is None
    assert item["device_status"] == "UNVERIFIED_CANDIDATE"
    assert item["speaker_ids"] == list(range(len(item["speaker_ids"])))
    assert {"MODEL_CARD", "model.onnx", "model.onnx.json"} == {f["name"] for f in item["files"]}
    assert item["dataset_license"] in {"CC0", "CC0 1.0 Universal", "public domain"}
    assert "Trained from scratch" in item["training_lineage"]
assert "sv_SE-nst-medium" in held_ids, "Unreconciled source card cannot be cleared implicitly"
print(
    f"Source-rights gate passed: {len(active_ids)} source-documented experimental candidate packs, "
    f"{sum(len(p['speaker_ids']) for p in approved['models'])} unverified slots; "
    f"{len(held_ids)} provenance hold(s); 0 verified voices."
)
