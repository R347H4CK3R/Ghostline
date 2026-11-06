#!/usr/bin/env python3
"""Source contract for included Piper native WAV replay and unverified evidence.

This does not prove physical-device inference or human listening.
"""
from pathlib import Path

source = Path("Ghostline/PiperIncludedVoiceStudio.swift").read_text()
required = [
    "AVAudioPlayerDelegate",
    "nonisolated func audioPlayerDidFinishPlaying(",
    "ObjectIdentifier(player)",
    "ObjectIdentifier(current) == id",
    "playbackCompleted = succeeded",
    "userAttestedListening = false",
    "func replaySavedWAV()",
    "try sha256File(wav) == expectedSHA256",
    "audioPlayer?.stop()",
    "replay.delegate = self",
    "audio.delegate = self",
    "func attestListening()",
    "guard !busy, playbackStarted, playbackCompleted, !userAttestedListening",
    '"device_audio_playback_completed": playbackCompleted',
    '"user_attested_listening": userAttestedListening',
    '"human_listening_confirmed": false',
    '"authorized_identity_match_confirmed": false',
    '"airplane_mode_confirmed": false',
    'Button("Replay SHA-checked WAV")',
    'Button("I listened to the completed WAV")',
    '.disabled(studio.busy || !studio.playbackCompleted || studio.userAttestedListening)',
]
missing = [token for token in required if token not in source]
assert not missing, f"Included Piper safety contracts missing: {missing}"
assert source.count("playbackCompleted = false") >= 3, "New sessions must clear stale replay completion"
assert source.count("userAttestedListening = false") >= 4, "New/repeated audio must clear stale listening acknowledgement"
assert source.index("audioPlayer = nil", source.index("func replaySavedWAV()")) < source.index("playbackStarted = replay.play()", source.index("func replaySavedWAV()"))
assert source.index("userAttestedListening = false", source.index("func replaySavedWAV()")) < source.index("replay.delegate = self", source.index("func replaySavedWAV()"))
print("Included Piper WAV replay/attestation receipt guard passed (device inference NOT verified)")
