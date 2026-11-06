import SwiftUI
import AVFoundation
import CryptoKit
import piper_player

// All bundled labels are candidates, never verified people or verified audio.
struct GhostlineIncludedPiperCatalog: Decodable {
    struct Asset: Decodable {
        let name: String
        let upstream_path: String
        let size: Int
        let sha256: String
    }
    struct Pack: Decodable, Identifiable {
        let id: String
        let display_name: String
        let engine: String
        let category: String
        let language: String
        let license: String
        let dataset_license: String
        let training_lineage: String
        let voice_usage_rights: String
        let device_status: String
        let model_card_url: String
        let speaker_ids: [Int]
        let files: [Asset]
        func asset(_ name: String) -> Asset? { files.first { $0.name == name } }
    }
    let schema_version: Int
    let source_repository: String
    let source_revision: String
    let repo_license: String
    let engine_runtime_license: String
    let models: [Pack]

    static func load() -> Self? {
        let file = Bundle.main.bundleURL.appendingPathComponent("PiperIncluded/manifest.json")
        guard let bytes = try? Data(contentsOf: file),
              let decoded = try? JSONDecoder().decode(Self.self, from: bytes),
              decoded.schema_version == 1 else { return nil }
        return decoded
    }
}

@MainActor
final class GhostlineIncludedPiperStudio: NSObject, ObservableObject, AVAudioPlayerDelegate {
    private let catalog = GhostlineIncludedPiperCatalog.load()
    @Published var selectedID = ""
    @Published var selectedSpeakerID = 0
    @Published var status = "These test packs are synthetic and UNVERIFIED on iPhone/Strata."
    @Published var busy = false
    @Published var outputURL: URL?
    @Published var evidenceURL: URL?
    @Published var playbackStarted = false
    @Published var playbackCompleted = false
    @Published var userAttestedListening = false

    private var engine: PiperPlayer?
    private var audioPlayer: AVAudioPlayer?
    private var activeModelSHA256: String?
    private var activeConfigSHA256: String?
    private var generatedAudioSHA256: String?
    var candidates: [GhostlineIncludedPiperCatalog.Pack] { catalog?.models ?? [] }
    var chosen: GhostlineIncludedPiperCatalog.Pack? { candidates.first { $0.id == selectedID } }
    var sourceRevision: String { catalog?.source_revision ?? "Not packaged" }

    override init() {
        super.init()
        selectedID = catalog?.models.first?.id ?? ""
        selectedSpeakerID = catalog?.models.first?.speaker_ids.first ?? 0
        if candidates.isEmpty { status = "No rights-documented included Piper packs in this IPA." }
    }

    func selectPack(_ id: String) {
        guard !busy, candidates.contains(where: { $0.id == id }) else { return }
        engine = nil
        audioPlayer?.stop()
        audioPlayer = nil
        selectedID = id
        selectedSpeakerID = chosen?.speaker_ids.first ?? 0
        outputURL = nil
        evidenceURL = nil
        playbackStarted = false
        playbackCompleted = false
        userAttestedListening = false
        generatedAudioSHA256 = nil
        activeModelSHA256 = nil
        activeConfigSHA256 = nil
        status = "Selected \(id). UNVERIFIED until iPhone offline audio is generated and reviewed."
    }

    func selectSpeaker(_ id: Int) {
        guard !busy, let pack = chosen, pack.speaker_ids.contains(id), selectedSpeakerID != id else { return }
        audioPlayer?.stop()
        audioPlayer = nil
        selectedSpeakerID = id
        outputURL = nil
        evidenceURL = nil
        generatedAudioSHA256 = nil
        playbackStarted = false
        playbackCompleted = false
        userAttestedListening = false
        status = "Selected speaker slot \(id) in \(pack.id): UNVERIFIED. Prior WAV receipt discarded."
    }

    private func packDirectory(for pack: GhostlineIncludedPiperCatalog.Pack) -> URL {
        Bundle.main.bundleURL.appendingPathComponent("PiperIncluded", isDirectory: true)
            .appendingPathComponent(pack.id, isDirectory: true)
    }

    private func sha256File(_ file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hash = SHA256()
        while let next = try handle.read(upToCount: 1024 * 1024), !next.isEmpty {
            hash.update(data: next)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func verify(_ asset: GhostlineIncludedPiperCatalog.Asset,
                        in dir: URL) throws -> String {
        guard ["model.onnx", "model.onnx.json", "MODEL_CARD"].contains(asset.name),
              asset.size > 0, asset.sha256.count == 64 else {
            throw NSError(domain: "GhostlinePiper", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid bundled asset manifest"])
        }
        let file = dir.appendingPathComponent(asset.name)
        let attrs = try FileManager.default.attributesOfItem(atPath: file.path)
        guard (attrs[.size] as? NSNumber)?.intValue == asset.size else {
            throw NSError(domain: "GhostlinePiper", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "Bundled asset length mismatch: \(asset.name)"])
        }
        let digest = try sha256File(file)
        guard digest == asset.sha256 else {
            throw NSError(domain: "GhostlinePiper", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Bundled asset SHA-256 mismatch: \(asset.name)"])
        }
        return digest
    }

    private func ensureEngine(for pack: GhostlineIncludedPiperCatalog.Pack) throws -> PiperPlayer {
        if let engine { return engine }
        guard pack.device_status == "UNVERIFIED_CANDIDATE",
              ["public domain", "CC0", "CC0 1.0 Universal"].contains(pack.dataset_license),
              pack.training_lineage.lowercased().contains("trained from scratch"),
              !pack.speaker_ids.isEmpty,
              pack.speaker_ids == Array(0..<pack.speaker_ids.count),
              pack.asset("model.onnx") != nil,
              pack.asset("model.onnx.json") != nil,
              pack.asset("MODEL_CARD") != nil else {
            throw NSError(domain: "GhostlinePiper", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "Pack provenance is not approved for inclusion"])
        }
        let directory = packDirectory(for: pack)
        let modelHash = try verify(pack.asset("model.onnx")!, in: directory)
        let configHash = try verify(pack.asset("model.onnx.json")!, in: directory)
        _ = try verify(pack.asset("MODEL_CARD")!, in: directory)
        let configFile = directory.appendingPathComponent("model.onnx.json")
        let configData = try Data(contentsOf: configFile)
        guard let config = try JSONSerialization.jsonObject(with: configData) as? [String: Any],
              (config["num_speakers"] as? Int ?? 1) == pack.speaker_ids.count else {
            throw NSError(domain: "GhostlinePiper", code: 5,
                          userInfo: [NSLocalizedDescriptionKey: "Unexpected speaker layout"])
        }
        let created = try PiperPlayer(params: .init(
            modelPath: directory.appendingPathComponent("model.onnx").path,
            configPath: configFile.path))
        self.engine = created
        activeModelSHA256 = modelHash
        activeConfigSHA256 = configHash
        return created
    }

    // The pinned Piper WAV writer leaves streaming placeholder lengths. Repair
    // the RIFF/data sizes before AVFoundation tries to read a multi-GB file.
    private func finalizeWAV(_ file: URL) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: file.path)
        guard let len = (attrs[.size] as? NSNumber)?.uint64Value,
              len >= 48, len - 8 <= UInt64(UInt32.max),
              (len - 44) % 4 == 0 else {
            throw NSError(domain: "GhostlinePiper", code: 6,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid Piper WAV length"])
        }
        let handle = try FileHandle(forUpdating: file)
        defer { try? handle.close() }
        guard let head = try handle.read(upToCount: 44), head.count == 44,
              head[0..<4].elementsEqual("RIFF".utf8),
              head[8..<12].elementsEqual("WAVE".utf8),
              head[12..<16].elementsEqual("fmt ".utf8),
              head[36..<40].elementsEqual("data".utf8),
              head[20] == 3, head[21] == 0,
              head[22] == 1, head[23] == 0,
              head[34] == 32, head[35] == 0 else {
            throw NSError(domain: "GhostlinePiper", code: 7,
                          userInfo: [NSLocalizedDescriptionKey: "Unexpected float WAV format"])
        }
        var riff = UInt32(len - 8).littleEndian
        var pcm = UInt32(len - 44).littleEndian
        try handle.seek(toOffset: 4)
        try handle.write(contentsOf: withUnsafeBytes(of: &riff) { Data($0) })
        try handle.seek(toOffset: 40)
        try handle.write(contentsOf: withUnsafeBytes(of: &pcm) { Data($0) })
    }

    func generate(_ phrase: String) async {
        guard !busy, let pack = chosen, pack.speaker_ids.contains(selectedSpeakerID) else { return }
        guard !phrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            status = "Enter text first."
            return
        }
        busy = true
        outputURL = nil
        evidenceURL = nil
        generatedAudioSHA256 = nil
        playbackStarted = false
        playbackCompleted = false
        userAttestedListening = false
        audioPlayer?.stop()
        audioPlayer = nil
        defer { busy = false }
        do {
            status = "Checking all three pinned model files offline (SHA-256)..."
            let player = try ensureEngine(for: pack)
            let escaped = phrase.replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
            guard let filePath = await player.synthesizeSSMLToFile(
                ssml: "<speak>\(escaped)</speak>", speakerId: Int32(selectedSpeakerID)) else {
                throw NSError(domain: "GhostlinePiper", code: 8,
                              userInfo: [NSLocalizedDescriptionKey: "No offline audio generated"])
            }
            let wav = URL(fileURLWithPath: filePath)
            try finalizeWAV(wav)
            let audio = try AVAudioPlayer(contentsOf: wav)
            guard audio.duration > 0.2, audio.prepareToPlay() else {
                throw NSError(domain: "GhostlinePiper", code: 9,
                              userInfo: [NSLocalizedDescriptionKey: "Generated WAV not decodable"])
            }
            let hash = try sha256File(wav)
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            audio.delegate = self
            audioPlayer = audio
            outputURL = wav
            generatedAudioSHA256 = hash
            playbackStarted = audio.play()
            status = playbackStarted
                ? "Generated local audio for \(pack.display_name). Playback started; human listening and airplane-mode confirmation still UNVERIFIED."
                : "WAV generated, but playback could not start. Audio remains UNVERIFIED."
        } catch {
            status = "Offline Piper candidate failed: \(error.localizedDescription)"
        }
    }

    // A prior player's delayed callback must not certify a newer WAV/replay.
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        let finishedID = ObjectIdentifier(player)
        Task { @MainActor [weak self] in
            self?.recordPlaybackCompletion(for: finishedID, succeeded: flag)
        }
    }

    private func recordPlaybackCompletion(for id: ObjectIdentifier, succeeded: Bool) {
        guard let current = audioPlayer, ObjectIdentifier(current) == id,
              outputURL != nil, generatedAudioSHA256 != nil, playbackStarted else { return }
        playbackCompleted = succeeded
        userAttestedListening = false
        evidenceURL = nil
        status = succeeded
            ? "Local WAV playback completed. You may acknowledge listening; voice identity and airplane-mode isolation remain UNVERIFIED."
            : "WAV playback did not complete successfully. Listening evidence remains UNVERIFIED."
    }

    func replaySavedWAV() {
        guard !busy, let wav = outputURL, let expectedSHA256 = generatedAudioSHA256 else { return }
        audioPlayer?.stop()
        audioPlayer = nil
        playbackStarted = false
        playbackCompleted = false
        userAttestedListening = false
        evidenceURL = nil
        do {
            guard try sha256File(wav) == expectedSHA256 else {
                throw NSError(domain: "GhostlinePiper", code: 10,
                              userInfo: [NSLocalizedDescriptionKey: "Saved WAV changed since generation"])
            }
            let replay = try AVAudioPlayer(contentsOf: wav)
            guard replay.duration > 0.2, replay.prepareToPlay() else {
                throw NSError(domain: "GhostlinePiper", code: 11,
                              userInfo: [NSLocalizedDescriptionKey: "WAV replay integrity check failed"])
            }
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            replay.delegate = self
            audioPlayer = replay
            playbackStarted = replay.play()
            status = playbackStarted
                ? "Replaying the same SHA-256-bound local WAV; completion and listening acknowledgement reset."
                : "Local replay did not start; no listening evidence recorded."
        } catch {
            status = "Cannot replay this candidate WAV: \(error.localizedDescription)"
        }
    }

    func attestListening() {
        guard !busy, playbackStarted, playbackCompleted, !userAttestedListening,
              outputURL != nil, generatedAudioSHA256 != nil else { return }
        userAttestedListening = true
        evidenceURL = nil
        status = "User acknowledged hearing completed local WAV. Rights, identity match, and airplane-mode isolation remain UNVERIFIED."
    }

    func exportEvidence() {
        guard let pack = chosen, let wav = outputURL,
              let modelHash = activeModelSHA256,
              let configHash = activeConfigSHA256,
              let audioHash = generatedAudioSHA256 else { return }
        guard (try? sha256File(wav)) == audioHash else {
            evidenceURL = nil
            status = "Saved WAV changed after generation; refusing a stale receipt."
            return
        }
        let record: [String: Any] = [
            "schema_version": 1, "engine": "Piper", "model_id": pack.id,
            "speaker_id": selectedSpeakerID, "speaker_slot_unverified": true,
            "source_model_card": pack.model_card_url,
            "model_sha256": modelHash, "config_sha256": configHash,
            "generated_wav_sha256": audioHash,
            "generated_wav_bytes": (try? wav.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0,
            "device_class": UIDevice.current.model,
            "ios_version": UIDevice.current.systemVersion,
            "candidate_not_verified": true,
            "device_audio_playback_started": playbackStarted,
            "device_audio_playback_completed": playbackCompleted,
            "user_attested_listening": userAttestedListening,
            "airplane_mode_confirmed": false,
            "human_listening_confirmed": false,
            "authorized_identity_match_confirmed": false,
            "license": pack.license,
            "source_revision": sourceRevision,
            "generated_utc": ISO8601DateFormatter().string(from: Date())
        ]
        do {
            let data = try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("ghostline-piper-unverified-\(UUID().uuidString).json")
            try data.write(to: file, options: .atomic)
            evidenceURL = file
            status = "Private evidence exported. Offline isolation, listening and identity remain unverified."
        } catch {
            status = "Evidence export failed: \(error.localizedDescription)"
        }
    }
}

struct GhostlineIncludedPiperView: View {
    @StateObject private var studio = GhostlineIncludedPiperStudio()
    @State private var phrase = "Welcome to Ghostline. This is an open-licensed offline voice test."
    var body: some View {
        Form {
            Section("Included test voices • UNVERIFIED") {
                Text("Source-checked open-license voices from public-domain recordings. No celebrity, actor, singer, or character identity claims.")
                    .font(.footnote).foregroundStyle(.secondary)
                Picker("Voice", selection: Binding(
                    get: { studio.selectedID },
                    set: { studio.selectPack($0) })) {
                    ForEach(studio.candidates) { pack in
                        Text(pack.display_name).tag(pack.id)
                    }
                }.disabled(studio.busy || studio.candidates.isEmpty)
                if let pack = studio.chosen {
                    Text("\(pack.language) • \(pack.license)")
                        .font(.footnote)
                    Text(pack.training_lineage)
                        .font(.caption).foregroundStyle(.secondary)
                    if let url = URL(string: pack.model_card_url) {
                        Link("Original model card / provenance", destination: url)
                    }
                }
                if let pack = studio.chosen, pack.speaker_ids.count > 1 {
                    Picker("Unverified speaker slot", selection: Binding(
                        get: { studio.selectedSpeakerID },
                        set: { studio.selectSpeaker($0) })) {
                        ForEach(pack.speaker_ids, id: \.self) { speakerID in
                            Text("Speaker slot \(speakerID) • UNVERIFIED").tag(speakerID)
                        }
                    }.disabled(studio.busy)
                }
                Text("No fixed pack or speaker-count cap. Multiple speaker IDs are candidate slots, not validated voices; included IPA audio remains UNVERIFIED.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Offline synthesis") {
                TextEditor(text: $phrase).frame(minHeight: 80)
                Button(studio.busy ? "Synthesizing..." : "Generate and play local WAV") {
                    Task { await studio.generate(phrase) }
                }.disabled(studio.busy || studio.candidates.isEmpty)
                if let wav = studio.outputURL {
                    ShareLink(item: wav) {
                        Label("Export unverified audio sample", systemImage: "square.and.arrow.up")
                    }
                    Button("Replay SHA-checked WAV") { studio.replaySavedWAV() }
                        .disabled(studio.busy)
                    Button("I listened to the completed WAV") { studio.attestListening() }
                        .disabled(studio.busy || !studio.playbackCompleted || studio.userAttestedListening)
                    Text(studio.playbackCompleted
                        ? "Playback completed; identity and offline isolation still unverified."
                        : "Listening acknowledgement unlocks only after native playback completes.")
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Export private SHA-256 test evidence") { studio.exportEvidence() }
                    if let evidence = studio.evidenceURL {
                        ShareLink(item: evidence) {
                            Label("Share unverified test receipt", systemImage: "doc.text")
                        }
                    }
                }
            }
            Section("Verification status") {
                Text(studio.status).font(.footnote)
                Text("0 voice identities verified. Airplane-mode isolation, completed playback, and human listening must be confirmed on the target iPhone/Strata.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Piper runtime GPL-3.0 obligations apply to redistribution of executables. Experimental unsigned IPA only.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Included Piper Voices")
    }
}
