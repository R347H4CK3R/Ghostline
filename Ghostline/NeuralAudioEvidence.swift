import SwiftUI
import AVFoundation
import CryptoKit

// Technical audio evidence only. Neither generated WAV bytes nor a preset name
// proves a person's identity, redistribution rights, or airplane-mode isolation.
private final class GhostlineNeuralPlaybackObserver: NSObject, AVAudioPlayerDelegate {
    var onFinished: ((Bool) -> Void)?
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        onFinished?(flag)
    }
    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        onFinished?(false)
    }
}

@MainActor
final class GhostlineNeuralAudioEvidence: ObservableObject {
    @Published private(set) var generatedWAV: URL?
    @Published private(set) var playbackCompleted = false
    @Published private(set) var userAttestedListening = false
    @Published private(set) var reportURL: URL?
    @Published private(set) var status = "Generate a WAV on the target iPhone to collect technical evidence."

    private struct Receipt {
        let engine: String
        let voiceID: String
        let wavSHA256: String
        let pcmSHA256: String
        let duration: Double
        let sampleRate: Int
        let channels: Int
        let createdUTC: String
    }
    private var receipt: Receipt?
    private var player: AVAudioPlayer?
    private var observer = GhostlineNeuralPlaybackObserver()
    private var attemptID = UUID()
    private var playbackSessionID = UUID()
    private var completionUTC: String?

    private static func digest(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }

    func reset() {
        attemptID = UUID()
        playbackSessionID = UUID()
        observer.onFinished = nil
        player?.stop()
        player?.delegate = nil
        player = nil
        if let old = generatedWAV { try? FileManager.default.removeItem(at: old) }
        generatedWAV = nil
        receipt = nil
        playbackCompleted = false
        userAttestedListening = false
        completionUTC = nil
        reportURL = nil
        status = "Audio evidence reset; no voice identity is verified."
    }

    @discardableResult
    func acceptGeneratedWAV(_ bytes: Data, engine: String, voiceID: String) throws -> URL {
        reset()
        let facts = try GhostlineWAVInspector.inspect(bytes)
        guard facts.durationSeconds >= 0.2 else {
            throw GhostlineWAVInspector.Failure.invalid("Audio is too short to evaluate")
        }
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent("GHOSTLINE-neural-" + UUID().uuidString + ".wav")
        do {
            try bytes.write(to: file, options: .atomic)
            receipt = Receipt(engine: engine, voiceID: voiceID,
                              wavSHA256: Self.digest(bytes), pcmSHA256: facts.pcmSHA256,
                              duration: facts.durationSeconds, sampleRate: facts.sampleRate,
                              channels: facts.channels,
                              createdUTC: ISO8601DateFormatter().string(from: Date()))
            generatedWAV = file
            try startNativePlayback(file)
            status = "Validated WAV generated; native playback started. Offline isolation, quality and identity unverified."
            return file
        } catch {
            reset()
            throw error
        }
    }

    // A new AVAudioPlayer and delegate for every replay make late completion
    // callbacks from a stopped/replaced player unable to certify current audio.
    private func startNativePlayback(_ file: URL) throws {
        guard let receipt, generatedWAV == file else {
            throw GhostlineWAVInspector.Failure.invalid("No current generated recording")
        }
        let currentBytes = try Data(contentsOf: file)
        let currentFacts = try GhostlineWAVInspector.inspect(currentBytes)
        guard Self.digest(currentBytes) == receipt.wavSHA256,
              currentFacts.pcmSHA256 == receipt.pcmSHA256 else {
            throw GhostlineWAVInspector.Failure.invalid("Generated WAV changed since synthesis")
        }
        observer.onFinished = nil
        player?.delegate = nil
        player?.stop()
        player = nil
        playbackCompleted = false
        userAttestedListening = false
        completionUTC = nil
        reportURL = nil
        playbackSessionID = UUID()

        try AVAudioSession.sharedInstance().setCategory(.playback)
        try AVAudioSession.sharedInstance().setActive(true)
        let replay = try AVAudioPlayer(contentsOf: file)
        guard replay.duration >= 0.2, replay.prepareToPlay() else {
            throw GhostlineWAVInspector.Failure.invalid("Generated WAV cannot be played natively")
        }
        let attempt = attemptID
        let session = playbackSessionID
        let currentObserver = GhostlineNeuralPlaybackObserver()
        currentObserver.onFinished = { [weak self] succeeded in
            DispatchQueue.main.async { [weak self] in
                guard let self, self.attemptID == attempt,
                      self.playbackSessionID == session,
                      self.generatedWAV == file else { return }
                self.playbackCompleted = succeeded
                self.completionUTC = succeeded ? ISO8601DateFormatter().string(from: Date()) : nil
                self.reportURL = nil
                self.status = succeeded
                    ? "Native playback finished. Confirm listening only if you heard the entire clip."
                    : "Native playback failed or ended early; listening cannot be confirmed."
            }
        }
        replay.delegate = currentObserver
        guard replay.play() else {
            throw GhostlineWAVInspector.Failure.invalid("Native WAV playback did not start")
        }
        observer = currentObserver
        player = replay
    }

    func replayGeneratedWAV() {
        guard let file = generatedWAV else {
            status = "Generate a WAV before replaying."
            return
        }
        do {
            try startNativePlayback(file)
            status = "Replaying the same SHA-256-checked WAV. Prior listening evidence cleared."
        } catch {
            reset()
            status = "Replay rejected; previous evidence invalidated: " + error.localizedDescription
        }
    }

    func attestListening() {
        guard playbackCompleted, generatedWAV != nil, !userAttestedListening else { return }
        userAttestedListening = true
        reportURL = nil
        status = "Full playback self-attested. Identity, rights and offline isolation remain unverified."
    }

    func exportPrivateEvidence() {
        guard let receipt, let file = generatedWAV else {
            status = "Generate a recording before exporting an evidence report."
            return
        }
        do {
            let currentBytes = try Data(contentsOf: file)
            let currentFacts = try GhostlineWAVInspector.inspect(currentBytes)
            guard Self.digest(currentBytes) == receipt.wavSHA256,
                  currentFacts.pcmSHA256 == receipt.pcmSHA256 else {
                throw GhostlineWAVInspector.Failure.invalid("Generated audio changed after recording")
            }
            let data: [String: Any] = [
                "schema_version": 1,
                "record_type": "ghostline_private_neural_audio_evidence",
                "generated_utc": ISO8601DateFormatter().string(from: Date()),
                "engine": receipt.engine, "voice_preset_id": receipt.voiceID,
                "wav_sha256": receipt.wavSHA256, "pcm_audio_payload_sha256": receipt.pcmSHA256,
                "wav_duration_seconds": receipt.duration,
                "sample_rate_hz": receipt.sampleRate, "channels": receipt.channels,
                "audio_created_utc": receipt.createdUTC,
                "native_playback_completed": playbackCompleted,
                "playback_completion_utc": completionUTC as Any? ?? NSNull(),
                "user_attested_listening": userAttestedListening,
                "model_weights_sha256": NSNull(),
                "airplane_mode_confirmed": false,
                "voice_identity_verified": false,
                "voice_rights_independently_verified": false,
                "perceptual_identity_review_confirmed": false
            ]
            let report = FileManager.default.temporaryDirectory
                .appendingPathComponent("GHOSTLINE-neural-private-" + UUID().uuidString + ".json")
            try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys])
                .write(to: report, options: .atomic)
            reportURL = report
            status = "Private technical report prepared. No identities or offline inference are certified."
        } catch {
            reportURL = nil
            status = "Evidence export rejected: " + error.localizedDescription
        }
    }
}

struct GhostlineNeuralEvidencePanel: View {
    @ObservedObject var evidence: GhostlineNeuralAudioEvidence
    var body: some View {
        Section("Device audio evidence • private") {
            if let wav = evidence.generatedWAV {
                ShareLink(item: wav) { Label("Export generated WAV", systemImage: "square.and.arrow.up") }
                Button("Replay WAV • clears listening confirmation") { evidence.replayGeneratedWAV() }
                if evidence.playbackCompleted {
                    Button(evidence.userAttestedListening ? "Full playback acknowledged" : "I heard the full WAV on this device") {
                        evidence.attestListening()
                    }
                    .disabled(evidence.userAttestedListening)
                }
                Button("Prepare private SHA-256 audio report") { evidence.exportPrivateEvidence() }
                if let report = evidence.reportURL {
                    ShareLink(item: report) {
                        Label("Export private diagnostic JSON", systemImage: "doc.text")
                    }
                }
            }
            Text(evidence.status).font(.footnote).foregroundStyle(.secondary)
            Text("Reports include the selected preset ID. WAV validity and listening do not prove identity, permission, or airplane-mode operation.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
