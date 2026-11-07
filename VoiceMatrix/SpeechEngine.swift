import Foundation
import Combine
import AVFoundation
import FluidAudio
import CoreML

actor NeuralSpeech {
    private var manager: PocketTtsSmallManager?
    private var session: PocketTtsSmallSession?
    private var activeVoice: String?
    private let computeUnits: MLComputeUnits
    init(computeUnits: MLComputeUnits = .cpuAndNeuralEngine) { self.computeUnits = computeUnits }
    func generate(text: String, voice: VoiceProfile, root: URL, manifest: VoiceManifest, output: URL, progress: @escaping @Sendable (String) -> Void = { _ in }) async throws -> Double {
        if manager == nil || activeVoice != voice.id {
            // Reset the manager on a profile switch: upstream caches every used voice's KV state.
            // One manager/profile at a time bounds that cache; measure load cost on device.
            progress("Checking included voice files")
            try Catalog.validate(root: root, manifest: manifest)
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
    func cancel() async { await session?.cancel() }
    func unload() async { await cancel(); manager = nil; activeVoice = nil }
}
@MainActor final class SpeechStudio: ObservableObject {
    @Published var voices: [VoiceProfile] = []
    @Published var selectedID = ""
    @Published var busy = false
    @Published var status = "Choose a voice, then type your words."
    @Published var output: URL?
    @Published var favorites = Set(UserDefaults.standard.stringArray(forKey: "favorites") ?? [])
    @Published var recent = UserDefaults.standard.stringArray(forKey: "recent") ?? []
    @Published var diagnostics = "VoiceMatrix 0.2.0\nNo device listening verification recorded.\n"
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
        } catch { status = error.localizedDescription }
    }
    func favorite(_ id: String) {
        if favorites.contains(id) { favorites.remove(id) } else { favorites.insert(id) }
        UserDefaults.standard.set(Array(favorites), forKey: "favorites")
    }
    func speak(_ text: String, audio: AudioStore) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, let voice = selected, let pack else { return }
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
                diagnostics += "synthesis engine=phonon31m profile=\(voice.id) seconds=\(duration) elapsed=\(Date().timeIntervalSince(started)) audible-listening=unverified\n"
                audio.play(url)
            } catch {
                try? FileManager.default.removeItem(at: url)
                guard generation == token else { return }
                busy = false; status = error is CancellationError ? "Stopped." : error.localizedDescription
                diagnostics += "synthesis result=failed code=\((error as NSError).code)\n"
            }
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
