import Foundation
import Combine
import AVFoundation

struct SavedAudio: Identifiable {
    var id: String { url.lastPathComponent }
    let url: URL
    var name: String { url.deletingPathExtension().lastPathComponent }
}
@MainActor final class AudioStore: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var recordings: [SavedAudio] = []
    @Published var playing: URL?
    @Published var error: String?
    @Published var rate: Float = 1
    private var player: AVAudioPlayer?
    var elapsedSeconds: TimeInterval { player?.currentTime ?? 0 }
    var durationSeconds: TimeInterval { player?.duration ?? 0 }
    #if os(iOS)
    var outputVolumePercent: Int { Int((AVAudioSession.sharedInstance().outputVolume * 100).rounded()) }
    var outputRoute: String {
        let outputs = AVAudioSession.sharedInstance().currentRoute.outputs
        // Show route types, never personal Bluetooth device names.
        return outputs.isEmpty ? "No audio output" : outputs.map { $0.portType.rawValue }.joined(separator: ", ")
    }
    #else
    // macOS does not expose AVAudioSession routes. No simulated route/volume.
    var outputVolumePercent: Int { -1 }
    var outputRoute: String { "System audio output" }
    #endif
    @Published private var activity = StudioActivity()
    var microphoneInUse: Bool { activity.microphoneInUse }
    var processingInUse: Bool { activity.processingInUse }
    func claimMicrophone() -> UUID? {
        guard let token = activity.claim(.microphone) else { return nil }
        stop(); return token
    }
    func releaseMicrophone(_ token: UUID) { activity.release(token) }
    func claimProcessing() -> UUID? { activity.claim(.processing) }
    func releaseProcessing(_ token: UUID) { activity.release(token) }
    private var savedSources = UserDefaults.standard.dictionary(forKey: "savedSources") as? [String: String] ?? [:]
    func isSaved(_ url: URL) -> Bool {
        let name = savedSources[url.lastPathComponent] ?? url.lastPathComponent
        return recordings.contains { $0.id == name }
    }
    private func persistSources() { UserDefaults.standard.set(savedSources, forKey: "savedSources") }
    private var recordingRoot: URL?
    private var folder: URL {
        recordingRoot ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Recordings", isDirectory: true)
    }
    override init() { super.init(); refresh() }
    init(recordingRoot: URL) { self.recordingRoot = recordingRoot; super.init(); refresh() }
    func refresh() {
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            recordings = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.creationDateKey])
                .filter { ["wav", "m4a", "caf"].contains($0.pathExtension) }
                .sorted { $0.lastPathComponent > $1.lastPathComponent }.map { SavedAudio(url: $0) }
        } catch { self.error = "Saved recordings could not be opened." }
    }
    func play(_ url: URL) {
        guard !microphoneInUse else { error = "Stop recording before listening to audio."; return }
        stop(); error = nil
        var stage = "configuring audio output"
        do {
            #if os(iOS)
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
            #endif
            stage = "opening the recording"
            let sound = try AVAudioPlayer(contentsOf: url)
            guard sound.duration > 0 else { throw StudioError.emptyAudio }
            sound.delegate = self; sound.enableRate = true; sound.rate = rate
            stage = "preparing playback"
            guard sound.prepareToPlay() else { throw StudioError.emptyAudio }
            player = sound
            stage = "starting playback"
            guard sound.play() else { throw StudioError.emptyAudio }
            playing = url
        } catch {
            stop()
            let failure = error as NSError
            self.error = "Could not play audio while \(stage) (\(failure.domain), code \(failure.code)). Try again or try another recording."
        }
    }
    func stop() { player?.stop(); player = nil; playing = nil }
    func save(_ url: URL) {
        do {
            guard !isSaved(url) else { return }
            _ = try AVAudioFile(forReading: url)
            try FileManager.default.copyItem(at: url, to: folder.appendingPathComponent(url.lastPathComponent))
            savedSources[url.lastPathComponent] = url.lastPathComponent; persistSources()
            refresh()
        } catch { self.error = "Your recording could not be saved. Check available storage." }
    }
    func delete(_ file: SavedAudio) {
        do { if playing == file.url { stop() }; try FileManager.default.removeItem(at: file.url); savedSources = savedSources.filter { $0.value != file.id }; persistSources(); refresh() }
        catch { self.error = "This recording could not be deleted." }
    }
    func rename(_ file: SavedAudio, to name: String) {
        let cleaned = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, cleaned.count <= 80, !cleaned.contains("/"), !cleaned.contains(":"), cleaned != ".", cleaned != ".." else { error = "Use a short name without slashes or colons."; return }
        do {
            let target = folder.appendingPathComponent(cleaned).appendingPathExtension(file.url.pathExtension)
            try FileManager.default.moveItem(at: file.url, to: target)
            for key in Array(savedSources.keys) where savedSources[key] == file.id { savedSources[key] = target.lastPathComponent }
            persistSources(); refresh()
        }
        catch { self.error = "That name is already used, or the recording could not be renamed." }
    }
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            guard self.player === player else { return }
            self.stop()
            if !flag { self.error = "Playback ended before the recording finished. Try replaying it." }
        }
    }
    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor in
            guard self.player === player else { return }
            self.stop()
            self.error = "The recording could not be decoded during playback. Try another recording."
        }
    }
}
