import Foundation
import Combine
import AVFoundation
import FluidAudio
import CoreML

actor NeuralSpeech {
    private var manager: PocketTtsSmallManager?
    private var session: PocketTtsSmallSession?
    private var activeVoice: String?
    private var validatedRoot: URL?
    private let converter: OfflineVoiceConverter
    private let computeUnits: MLComputeUnits
    static var defaultComputeUnits: MLComputeUnits {
        #if targetEnvironment(simulator)
        return .cpuOnly
        #else
        return .cpuAndNeuralEngine
        #endif
    }
    init(computeUnits: MLComputeUnits = NeuralSpeech.defaultComputeUnits) { self.computeUnits = computeUnits; self.converter = OfflineVoiceConverter(computeUnits: computeUnits == .cpuOnly ? .cpuOnly : .cpuAndGPU) }
    func generate(text: String, voice: VoiceProfile, root: URL, manifest: VoiceManifest, output: URL, progress: @escaping @Sendable (String) -> Void = { _ in }) async throws -> Double {
        try Task.checkCancellation()
        if voice.engine == "phonon31m-openvoicev2" {
            return try await generateConditioned(text: text, voice: voice, root: root, manifest: manifest, output: output, progress: progress)
        }
        guard voice.engine == "phonon31m" else { throw StudioError.invalidAsset("voice engine") }
        await converter.releaseModels()
        return try await generateRaw(text: text, voice: voice, root: root, manifest: manifest, output: output, progress: progress)
    }
    private func generateRaw(text: String, voice: VoiceProfile, root: URL, manifest: VoiceManifest, output: URL, progress: @escaping @Sendable (String) -> Void) async throws -> Double {
        if manager == nil || activeVoice != voice.id {
            // Reset the manager on a profile switch: upstream caches every used voice's KV state.
            // One manager/profile at a time bounds that cache; measure load cost on device.
            progress("Checking included voice files")
            if validatedRoot != root { try Catalog.validate(root: root, manifest: manifest); validatedRoot = root }
            manager = nil
            let fresh = PocketTtsSmallManager(model: .phonon31m, computeUnits: computeUnits)
            progress("Starting the voice engine")
            try await fresh.load(from: root) // Local-only API. Never initialize()/download.
            manager = fresh; activeVoice = voice.id
        }
        guard let manager else { throw StudioError.missingPack }
        try Task.checkCancellation()
        progress("Preparing the selected voice")
        let stream = try await manager.makeSession(voice: voice.id)
        progress("Creating your speech")
        session = stream
        stream.enqueue(text); stream.finish()
        var writer: AVAudioFile?
        var frames: Int64 = 0; var energy: Double = 0
        do {
        writer = try AVAudioFile(forWriting: output, settings: [
            AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0,
            AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false
        ])
            guard let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1) else { throw StudioError.emptyAudio }
            for try await frame in stream.frames {
                try Task.checkCancellation()
                if frames == 0 { progress("Writing speech audio") }
                guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frame.samples.count)), let samples = buffer.floatChannelData?[0] else { throw StudioError.emptyAudio }
                buffer.frameLength = AVAudioFrameCount(frame.samples.count)
                for (index, value) in frame.samples.enumerated() {
                    guard value.isFinite else { throw StudioError.emptyAudio }
                    samples[index] = max(-1, min(1, value)); energy += Double(value) * Double(value)
                }
                try writer?.write(from: buffer); frames += Int64(frame.samples.count)
            }
            try Task.checkCancellation()
            progress("Finishing your recording")
            writer = nil; session = nil
            guard frames >= 2400, energy / Double(frames) > 1e-9 else { throw StudioError.emptyAudio }
            let decoded = try AVAudioFile(forReading: output)
            guard decoded.length == frames else { throw StudioError.emptyAudio }
            return Double(frames) / 24000
        } catch {
            await stream.cancel(); writer = nil; session = nil
            try? FileManager.default.removeItem(at: output); throw error
        }
    }
    private func generateConditioned(text: String, voice: VoiceProfile, root: URL, manifest: VoiceManifest, output: URL, progress: @escaping @Sendable (String) -> Void) async throws -> Double {
        guard let baseID = voice.baseVoiceID, let base = manifest.voices.first(where: { $0.id == baseID && $0.engine == "phonon31m" }) else { throw StudioError.invalidAsset("voice source") }
        if validatedRoot != root { try Catalog.validate(root: root, manifest: manifest); validatedRoot = root }
        let target = try await converter.targetProfile(for: voice, root: root, manifest: manifest)
        var queue = SpeechTextChunks.split(text)
        guard !queue.isEmpty else { throw StudioError.emptyAudio }
        var clips: [URL] = []; var temporary: [URL] = []
        defer { for url in temporary { TemporaryAudio.discard(url) } }
        do {
            while !queue.isEmpty {
                try Task.checkCancellation()
                let part = queue.removeFirst()
                let source = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-\(UUID().uuidString).wav")
                let changed = FileManager.default.temporaryDirectory.appendingPathComponent("Converted-\(UUID().uuidString).wav")
                temporary += [source, changed]
                await converter.releaseModels()
                progress("Creating part \(clips.count + 1) of your message")
                let duration = try await generateRaw(text: part, voice: base, root: root, manifest: manifest, output: source, progress: progress)
                if duration > 10 {
                    let words = part.split(whereSeparator: \.isWhitespace).map(String.init)
                    guard words.count > 1 else { throw StudioError.textTooLongForVoice }
                    let middle = words.count / 2
                    queue.insert(contentsOf: [words[..<middle].joined(separator: " "), words[middle...].joined(separator: " ")], at: 0)
                    continue
                }
                manager = nil; activeVoice = nil
                _ = try await converter.convert(source: source, target: target.embedding, destination: changed, progress: progress)
                clips.append(changed)
            }
            try Task.checkCancellation()
            return try ConvertedAudioAssembler.join(clips, to: output)
        } catch { try? FileManager.default.removeItem(at: output); throw error }
    }
    func convertRecording(source: URL, voice: VoiceProfile, root: URL, manifest: VoiceManifest, output: URL, progress: @escaping @Sendable (String) -> Void) async throws -> Double {
        try Task.checkCancellation()
        await session?.cancel(); session = nil; manager = nil; activeVoice = nil
        if validatedRoot != root { try Catalog.validate(root: root, manifest: manifest); validatedRoot = root }
        let target = try await converter.targetProfile(for: voice, root: root, manifest: manifest)
        return try await converter.convert(source: source, target: target.embedding, destination: output, progress: progress).outputSeconds
    }
    func cancel() async { await session?.cancel() }
    func unload() async { await cancel(); manager = nil; activeVoice = nil; validatedRoot = nil; await converter.unload() }
}
@MainActor final class SpeechStudio: ObservableObject {
    @Published var automatedChecks = 0
    @Published var voices: [VoiceProfile] = []
    @Published var selectedID = ""
    @Published var busy = false
    @Published var recordingInProgress = false
    @Published var changingVoice = false
    @Published var checkingVoices = false
    @Published var checkProgress = 0.0
    @Published var onDeviceSpeechChecks = 0
    @Published var status = "Choose a voice, then type your words."
    @Published var output: URL?
    @Published var changedOutput: URL?
    @Published var favorites = Set(UserDefaults.standard.stringArray(forKey: "favorites") ?? [])
    @Published var recent = UserDefaults.standard.stringArray(forKey: "recent") ?? []
    @Published var diagnostics = "VoiceMatrix \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development")\nNo device listening verification recorded.\n"
    private let neural = NeuralSpeech()
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var pack: (URL, VoiceManifest)?
    var selected: VoiceProfile? { voices.first { $0.id == selectedID } }
    init() {
        AppLogger.minimumLevel = .fault
        AppLogger.mirrorsToConsole = false
        do {
            let loaded = try Catalog.read(); pack = loaded
            voices = loaded.1.voices.sorted { a, b in
                if (a.accent == "American") != (b.accent == "American") { return a.accent == "American" }
                return a.name < b.name
            }
            selectedID = voices.first?.id ?? ""
            let local = DeviceVoiceChecks.load(manifest: loaded.1)
            onDeviceSpeechChecks = local.physicalDevice ? local.checkedProfiles.count : 0
            let proofURL = loaded.0.appendingPathComponent("voice-synthesis-results.json")
            if let data = try? Data(contentsOf: proofURL),
               let proof = try? JSONDecoder().decode(SynthesisProof.self, from: data),
               proof.modelRevision == loaded.1.revision,
               proof.profiles.count == voices.count,
               Set(proof.profiles.map(\.id)) == Set(voices.map(\.id)),
               proof.profiles.allSatisfy({ item in item.nonSilentWAVDecoded && item.audioSeconds > 0.1 && voices.contains(where: { $0.id == item.id && $0.sha256 == item.embeddingSHA256 }) }) {
                automatedChecks = proof.profiles.count
            }
        } catch { status = error.localizedDescription }
    }
    func favorite(_ id: String) {
        if favorites.contains(id) { favorites.remove(id) } else { favorites.insert(id) }
        UserDefaults.standard.set(Array(favorites), forKey: "favorites")
    }
    func speak(_ text: String, audio: AudioStore) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, !recordingInProgress, let voice = selected, let pack else { return }
        guard !text.isEmpty, text.count <= 2000 else { status = "Enter between 1 and 2,000 characters."; return }
        audio.stop(); TemporaryAudio.discard(output); busy = true; status = "Preparing \(voice.name)…"; output = nil
        let token = UUID(); generation = token
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-\(UUID().uuidString).wav")
        task = Task {
            let started = Date()
            do {
                let duration = try await neural.generate(text: text, voice: voice, root: pack.0, manifest: pack.1, output: url, progress: { [weak self] phase in
                    Task { @MainActor [weak self] in
                        guard let self, self.generation == token, self.busy else { return }
                        self.status = phase
                    }
                })
                try Task.checkCancellation()
                guard generation == token else { try? FileManager.default.removeItem(at: url); return }
                output = url; busy = false; status = "Ready. Listen, Save, or Share."
                recent = [voice.id] + Array(recent.filter { $0 != voice.id }.prefix(9))
                UserDefaults.standard.set(recent, forKey: "recent")
                diagnostics += "synthesis engine=\(voice.engine) profile=\(voice.id) seconds=\(duration) elapsed=\(Date().timeIntervalSince(started)) audible-listening=unverified\n"
                audio.play(url)
            } catch {
                try? FileManager.default.removeItem(at: url)
                guard generation == token else { return }
                busy = false; status = error is CancellationError || Task.isCancelled ? "Stopped." : error.localizedDescription
                diagnostics += "synthesis result=failed code=\((error as NSError).code)\n"
            }
        }
    }
    func changeVoice(source: URL, audio: AudioStore) {
        guard !busy, !recordingInProgress, let voice = selected, let pack else { return }
        audio.stop(); TemporaryAudio.discard(changedOutput); changedOutput = nil
        busy = true; changingVoice = true; status = "Preparing \(voice.name)…"
        let token = UUID(); generation = token
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("Converted-\(UUID().uuidString).wav")
        task = Task {
            let started = Date()
            do {
                let duration = try await neural.convertRecording(source: source, voice: voice, root: pack.0, manifest: pack.1, output: url, progress: { [weak self] phase in
                    Task { @MainActor [weak self] in
                        guard let self, self.generation == token, self.busy else { return }
                        self.status = phase
                    }
                })
                try Task.checkCancellation()
                guard generation == token else { TemporaryAudio.discard(url); return }
                changedOutput = url; busy = false; changingVoice = false; status = "Your changed voice is ready. Listen, Save, or Share."
                recent = [voice.id] + Array(recent.filter { $0 != voice.id }.prefix(9))
                UserDefaults.standard.set(recent, forKey: "recent")
                diagnostics += "conversion profile=\(voice.id) seconds=\(duration) elapsed=\(Date().timeIntervalSince(started)) audible-listening=unverified\n"
                audio.play(url)
            } catch {
                TemporaryAudio.discard(url)
                guard generation == token else { return }
                busy = false; changingVoice = false; status = error is CancellationError || Task.isCancelled ? "Stopped." : error.localizedDescription
                diagnostics += "conversion result=failed code=\((error as NSError).code)\n"
            }
        }
    }
    func clearChangedVoice() { TemporaryAudio.discard(changedOutput); changedOutput = nil }
    func checkIncludedVoices(audio: AudioStore) {
        guard !busy, !recordingInProgress, let pack else { return }
        audio.stop(); busy = true; checkingVoices = true; checkProgress = 0
        let token = UUID(); generation = token
        task = Task {
            var report = DeviceVoiceChecks.load(manifest: pack.1)
            var processed = 0
            for voice in voices {
                if Task.isCancelled { break }
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-Check-\(UUID().uuidString).wav")
                status = "Checking \(processed + 1) of \(voices.count): \(voice.name)"
                do {
                    _ = try await neural.generate(text: "Hello. This is a voice test.", voice: voice, root: pack.0, manifest: pack.1, output: url)
                    try Task.checkCancellation()
                    report.checkedProfiles[voice.id] = voice.sha256
                    report.failures.removeValue(forKey: voice.id)
                } catch {
                    if !Task.isCancelled { report.checkedProfiles.removeValue(forKey: voice.id); report.failures[voice.id] = (error as NSError).code }
                }
                TemporaryAudio.discard(url)
                processed += 1; checkProgress = Double(processed) / Double(voices.count)
                onDeviceSpeechChecks = report.physicalDevice ? report.checkedProfiles.count : 0
                if processed % 10 == 0 { report.checkedAt = Date(); report.save() }
            }
            await neural.unload()
            report.checkedAt = Date(); report.save()
            guard generation == token else { return }
            onDeviceSpeechChecks = report.physicalDevice ? report.checkedProfiles.count : 0
            busy = false; checkingVoices = false
            status = Task.isCancelled ? "Checks stopped. Completed results were saved." : "Checked \(processed) voices. \(report.failures.count) could not produce audio."
            diagnostics += "local-voice-checks physical=\(report.physicalDevice) passed=\(report.checkedProfiles.count) failed=\(report.failures.count) listening=unverified\n"
        }
    }
    func cancel() {
        task?.cancel(); status = "Stopping…"
        Task { await neural.cancel() }
    }
    func memoryWarning() { if !busy { Task { await neural.unload() } }; diagnostics += "memory-warning\n" }
    func diagnosticFile() -> URL? {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("VoiceMatrix-diagnostics.txt")
        do { try diagnostics.write(to: url, atomically: true, encoding: .utf8); return url } catch { status = "The error report could not be created."; return nil }
    }
}

private struct SynthesisProof: Decodable {
    struct Entry: Decodable { let id, embeddingSHA256: String; let audioSeconds: Double; let nonSilentWAVDecoded: Bool }
    let modelRevision: String
    let profiles: [Entry]
}
