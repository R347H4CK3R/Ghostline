"""Source contracts for experimental PocketTTS/Kokoro physical-device receipts.
These are regression guards, not simulated proof of iPhone audio generation.
"""
from pathlib import Path

evidence = Path("Ghostline/NeuralAudioEvidence.swift").read_text()
kokoro = Path("Ghostline/KokoroOffline.swift").read_text()
pocket = Path("Ghostline/NeuralStudio.swift").read_text()

required = (
    "GhostlineWAVInspector.inspect(bytes)",
    "facts.durationSeconds >= 0.2",
    "AVAudioPlayer(contentsOf: file)",
    "guard replay.play()",
    "func audioPlayerDidFinishPlaying",
    "self.attemptID == attempt",
    "self.generatedWAV == file",
    "self.playbackCompleted = succeeded",
    "guard playbackCompleted, generatedWAV != nil, !userAttestedListening",
    "currentFacts.pcmSHA256 == receipt.pcmSHA256",
    "Self.digest(currentBytes) == receipt.wavSHA256",
    '"model_weights_sha256": NSNull()',
    '"airplane_mode_confirmed": false',
    '"voice_identity_verified": false',
    '"voice_rights_independently_verified": false',
    '"perceptual_identity_review_confirmed": false',
    '"user_attested_listening": userAttestedListening',
    "observer.onFinished = nil",
    "player?.stop()",
)
for invariant in required:
    assert invariant in evidence, f"Missing neural evidence contract: {invariant}"
assert evidence.index("reset()\n        let facts =") < evidence.index("let replay = try AVAudioPlayer")
assert "func attestListening()" in evidence
assert "func exportPrivateEvidence()" in evidence

for name, source, engine in [("Kokoro", kokoro, "Kokoro"),
                              ("PocketTTS", pocket, "PocketTTS")]:
    assert 'let evidence = GhostlineNeuralAudioEvidence()' in source, name
    assert 'let selectedVoice = voiceID' in source, name
    assert f'evidence.acceptGeneratedWAV(wav, engine: "{engine}", voiceID: selectedVoice)' in source, name
    assert "clearOutput()" in source and ".disabled(" in source, name
    assert "GhostlineNeuralEvidencePanel(evidence:" in source, name
    assert "AVSpeechSynthesizer" not in source, name

print("PocketTTS/Kokoro native audio-evidence source contracts passed.")
print("No CI result is target-device playback or identity verification.")
