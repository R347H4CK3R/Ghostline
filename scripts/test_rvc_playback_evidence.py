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
