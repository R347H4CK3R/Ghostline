#!/usr/bin/env python3
"""Static wiring regression guard; NOT a target-iPhone playback test."""
from pathlib import Path
s=Path("Ghostline/OfflineRVCWeb.swift").read_text()
required=["GhostlineRVCPlaybackObserver: NSObject, AVAudioPlayerDelegate",
"func audioPlayerDidFinishPlaying", "replay.delegate = playbackObserver",
"self.playbackAttemptID == attempt", "self.latestWAV == file",
'(self.savedWAV?["sha256"] as? String) == digest',
'self.savedWAV?["device_audio_playback_completed"] = true',
'guard playbackStarted, playbackCompleted, latestWAV != nil, !userAttestedListening',
'if controller.playbackCompleted',
'"target_device_audio_listening_user_attested": userAttestedListening',
'"airplane_mode_confirmed": false','"voice_identity_verified": false']
assert all(x in s for x in required),[x for x in required if x not in s]
assert s.count("playbackAttemptID = UUID()")>=3
assert s.count("playbackObserver.onFinished = nil")>=3
print("Native completion delegate, stale-playback protection, SHA-bound evidence: PASS")


# Regression contract for async generation attempts: no stale audio/evidence.
b=Path("scripts/build_offline_rvc_web.py").read_text()
assert 'kind: "conversion_started", conversionId: conversionID' in b
assert 'kind: "wav", conversionId: conversionID' in b
assert 'previousPreview.removeAttribute("src")' in b
assert 'previousSave.hidden = true' in b
assert 'previousSave.removeAttribute("href")' in b
assert 'func beginConversion(id: String)' in s
assert 'guard activeConversionID == conversionID else' in s
assert 'event("stale_wav_rejected"' in s
assert '"conversion_attempt_id": conversionID' in s
assert 'activeConversionID = nil // reject duplicate or delayed exports' in s
assert 'activeConversionID = nil // reject late WKWebView audio' in s
start=s.split("func beginConversion(id: String)",1)[1].split("func receiveAudio(",1)[0]
for token in ['player?.stop()', 'playbackCompleted = false',
              'userAttestedListening = false', 'latestWAV = nil',
              'savedWAV = nil', 'activeConversionID = id']:
    assert token in start, token
assert b.index('kind: "conversion_started"') < b.index('const decoded = await prepareInputAudio(audio)')
print("New generation clears browser/native stale audio and binds exports to their attempt: PASS")
