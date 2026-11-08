#!/usr/bin/env python3
"""Source wiring guard only; Swift fixture tests exercise the shared inspector.
This does not establish physical-device synthesis or human listening.
"""
from pathlib import Path

source = Path("Ghostline/PiperIncludedVoiceStudio.swift").read_text()
generation = source.split("func generate(_ phrase: String)", 1)[1].split("nonisolated func audioPlayerDidFinishPlaying", 1)[0]
assert "GhostlineWAVInspector.inspect" in generation, "Included Piper must inspect PCM, not merely WAV duration"
assert generation.index("try finalizeWAV(wav)") < generation.index("GhostlineWAVInspector.inspect")
assert generation.index("GhostlineWAVInspector.inspect") < generation.index("AVAudioPlayer(contentsOf: wav)")
assert generation.index("GhostlineWAVInspector.inspect") < generation.index("outputURL = wav")
assert "generatedPCMHash = facts.pcmSHA256" in generation
for start, end in (("func selectPack(", "func selectSpeaker("),
                   ("func selectSpeaker(", "private func packDirectory("),
                   ("func generate(", "nonisolated func audioPlayerDidFinishPlaying")):
    operation = source.split(start, 1)[1].split(end, 1)[0]
    assert "generatedPCMHash = nil" in operation, f"{start} must discard PCM evidence"
evidence = source.split("func exportEvidence()", 1)[1].split("struct GhostlineIncludedPiperView", 1)[0]
assert "let pcmHash = generatedPCMHash" in evidence
assert '"pcm_audio_payload_sha256": pcmHash' in evidence
assert '"airplane_mode_confirmed": false' in evidence
assert '"authorized_identity_match_confirmed": false' in evidence
print("Included Piper PCM inspection wiring passed (device behavior NOT verified)")
