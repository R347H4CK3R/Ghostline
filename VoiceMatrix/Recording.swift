import SwiftUI
import AVFoundation
import UniformTypeIdentifiers

@MainActor final class Recorder: ObservableObject {
    @Published var recording = false
    @Published var output: URL?
    @Published var status = "Record your voice or import an audio file."
    private var recorder: AVAudioRecorder?
    private var timer: Task<Void, Never>?
    private var requestID = UUID()
    func start() async {
        guard !recording else { return }
        let request = UUID(); requestID = request
        let permitted = await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in AVAudioApplication.requestRecordPermission { c.resume(returning: $0) } }
        guard requestID == request else { return }
        guard permitted else { status = "Allow microphone access in iPhone Settings → Apps → VoiceMatrix."; return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker]); try session.setActive(true)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("Recording-\(UUID().uuidString).wav")
            let rec = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
            guard rec.record(forDuration: 120) else { throw StudioError.emptyAudio }
            recorder = rec; output = url; recording = true; status = "Recording… Tap Stop when finished. Maximum 2 minutes."
            timer = Task { try? await Task.sleep(nanoseconds: 120_000_000_000); if !Task.isCancelled { stop() } }
        } catch { status = "The microphone could not start. Check permission and available storage." }
    }
    func stop() {
        requestID = UUID()
        recorder?.stop(); recorder = nil; recording = false; timer?.cancel(); timer = nil
        guard let output, let file = try? AVAudioFile(forReading: output), file.length > 0 else { self.output = nil; status = "No audio was recorded. Try again."; return }
        status = "Your original recording is ready."
    }
    func importAudio(_ url: URL) {
        guard !recording else { return }
        let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
        do {
            let source = try AVAudioFile(forReading: url)
            guard source.length > 0, Double(source.length) / source.fileFormat.sampleRate <= 120 else { status = "Choose an audio file under 2 minutes."; return }
            let target = FileManager.default.temporaryDirectory.appendingPathComponent("Imported-\(UUID().uuidString).wav")
            var writer: AVAudioFile? = try AVAudioFile(forWriting: target, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: source.processingFormat.sampleRate, AVNumberOfChannelsKey: Int(source.processingFormat.channelCount), AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
            guard let buffer = AVAudioPCMBuffer(pcmFormat: source.processingFormat, frameCapacity: 8192) else { throw StudioError.emptyAudio }
            do {
                while source.framePosition < source.length { try source.read(into: buffer); try writer?.write(from: buffer) }
                writer = nil
            } catch { writer = nil; try? FileManager.default.removeItem(at: target); throw error }
            output = target; status = "Your original audio is ready."
        } catch { status = "That file could not be opened. Try a WAV, M4A, or CAF file." }
    }
}
struct RecordingView: View {
    @StateObject private var recorder = Recorder()
    @EnvironmentObject var audio: AudioStore
    @EnvironmentObject var studio: SpeechStudio
    @State private var importing = false
    var body: some View {
        Form {
            Section("Step 1 · Record or import") {
                Button {
                    audio.stop()
                    if recorder.recording { recorder.stop() } else { Task { await recorder.start() } }
                } label: { Label(recorder.recording ? "STOP RECORDING" : "RECORD MY VOICE", systemImage: recorder.recording ? "stop.fill" : "mic.fill").frame(minHeight: 52) }.buttonStyle(.borderedProminent).disabled(studio.busy)
                Button("Import Audio") { importing = true }.disabled(recorder.recording)
                Text(recorder.status)
            }
            Section("Voice conversion") {
                Text("Not included yet").font(.headline)
                Text("This experimental build can record, import, listen, and save your original audio. A tested voice conversion engine is still required to change it into another voice.")
            }
            if let url = recorder.output, !recorder.recording { Section("Listen or Save Original Audio") { AudioActions(url: url) } }
        }.navigationTitle("Change My Voice").onDisappear { recorder.stop() }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.wav, .mpeg4Audio, .audio]) { result in
                switch result { case .success(let url): recorder.importAudio(url); case .failure: recorder.status = "Import was cancelled or the file could not be opened." }
            }
    }
}
