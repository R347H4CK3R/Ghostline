#!/usr/bin/env python3
"""Static source/provenance check. NOT proof of device inference or listening."""
import json
import re
from pathlib import Path
catalog=json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text(encoding="utf-8"))
assert catalog["verified_identity_count"] == 0 == catalog["device_verified_audio_count"]
assert catalog["distribution_scope"].startswith("experimental unsigned IPA")
assert len(catalog["models"]) >= 7
assert len({p["id"] for p in catalog["models"]}) == len(catalog["models"])
assert sum(len(p["speaker_ids"]) for p in catalog["models"]) >= 9
rev=catalog["source_revision"]
for p in catalog["models"]:
    assert re.fullmatch(r"[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(?:x_low|low|medium|high)",p["id"])
    assert p["claimed_real_person_identity"] is None and p["device_status"]=="UNVERIFIED_CANDIDATE"
    assert p["dataset_license"] in ("public domain","CC0","CC0 1.0 Universal")
    assert p["speaker_ids"] == list(range(len(p["speaker_ids"]))) and p["speaker_ids"]
    assert p["model_card_url"].startswith("https://huggingface.co/rhasspy/piper-voices/blob/"+rev+"/")
    assert {f["name"] for f in p["files"]} == {"model.onnx","model.onnx.json","MODEL_CARD"}
    for f in p["files"]:
        assert f["size"]>0 and re.fullmatch(r"[0-9a-f]{64}",f["sha256"])
        assert f["upstream_path"] and ".." not in f["upstream_path"]
by_id={p["id"]:p for p in catalog["models"]}
for derivative, parent, phrase in (
    ("en_US-john-medium", "en_US-kristin-medium", "Finetuned from Kristin (above)"),
    ("nl_NL-alex-medium", "nl_BE-rdh-medium", "Finetuned from Dutch rdh voice"),
):
    p=by_id[derivative]
    assert p["parent_model_id"] == parent and p["parent_lineage_card_phrase"] == phrase
    assert "Finetuned from" in p["training_lineage"]
    assert "Trained from scratch" in by_id[parent]["training_lineage"]
    assert p["rights_review"]["parent_model_source_url"] == by_id[parent]["model_card_url"]
    assert p["device_status"] == "UNVERIFIED_CANDIDATE"
assert by_id["nl_BE-rdh-medium"]["dataset_license"]=="CC0 1.0 Universal"
assert by_id["nl_BE-rdh-x_low"]["dataset_license"]=="CC0 1.0 Universal"
assert by_id["nl_BE-rdh-x_low"]["dataset_source_url"]==by_id["nl_BE-rdh-medium"]["dataset_source_url"]
assert by_id["nl_BE-rdh-x_low"]["speaker_ids"]==[0]
assert next(f for f in by_id["nl_BE-rdh-x_low"]["files"] if f["name"]=="model.onnx")["size"] < 25_000_000
assert by_id["nl_BE-rdh-x_low"]["rights_review"]["decision"]=="SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY"
assert by_id["uk_UA-ukrainian_tts-medium"]["speaker_ids"]==[0,1,2]
# November 6 expansion: source-declared slots are candidate IDs, never target-device proof.
for key in ("no_NO-nvcc-medium", "nl_BE-nathalie-x_low", "el_GR-rapunzelina-medium"):
    item=by_id[key]
    assert item["device_status"]=="UNVERIFIED_CANDIDATE"
    assert item["dataset_license"]=="CC0"
    assert item["dataset_source_url"].startswith("https://")
    assert "Trained from scratch" in item["training_lineage"]
    assert item["claimed_real_person_identity"] is None
assert by_id["no_NO-nvcc-medium"]["speaker_ids"]==list(range(10))
assert by_id["nl_BE-nathalie-x_low"]["speaker_ids"]==[0]
assert by_id["el_GR-rapunzelina-medium"]["speaker_ids"]==[0]
assert by_id["el_GR-rapunzelina-medium"]["dataset_source_url"] == "https://www.kaggle.com/datasets/bryanpark/greek-single-speaker-speech-dataset"
assert "sv_SE-nst-medium" not in by_id
# Original Swedish MODEL_CARD confuses NST dictation sbr-17 with TTS sbr-18.
# Preserve its source history ONLY in a non-distributable quarantine ledger.
quarantine=json.loads(Path("Ghostline/Resources/quarantined-piper-candidates.json").read_text(encoding="utf-8"))
sv = next(p for p in quarantine["models"] if p["id"] == "sv_SE-nst-medium")
assert sv["rights_review"]["not_for_distribution"] is True
assert sv["dataset_source_url"] == "https://kb-labb.github.io/posts/2023-05-24-swedish-text-to-speech/"
assert sv["dataset_historical_catalogue_url"].endswith("/oai-nb-no-sbr-18/")
assert "sbr-17" in sv["dataset_provenance_note"] and "sbr-18" in sv["dataset_provenance_note"]
assert "source-reported" in sv["dataset_provenance_note"].lower()
source=Path("Ghostline/PiperIncludedVoiceStudio.swift").read_text()
assert "speakerId: Int32(selectedSpeakerID)" in source
assert '"speaker_id": selectedSpeakerID' in source
assert '"speaker_slot_unverified": true' in source
assert "func selectSpeaker(_ id: Int)" in source
reset=source.split("func selectSpeaker(_ id: Int)",1)[1].split("private func packDirectory",1)[0]
for marker in ("outputURL = nil","evidenceURL = nil","playbackCompleted = false","userAttestedListening = false"):
    assert marker in reset
assert "Task.detached(priority: .userInitiated)" in source
assert "try await ensureEngine(for: pack)" in source
assert "ghostlineVerifyIncludedAsset(" in source
assert "checksByName" in source
assert "0 voice identities verified" in source
print(f"Provenance: {len(catalog['models'])} unverified model packs; {sum(len(p['speaker_ids']) for p in catalog['models'])} candidate speaker slots; 0 verified device voices.")
