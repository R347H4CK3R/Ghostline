import SwiftUI
import AVFoundation
import UniformTypeIdentifiers

@MainActor final class Recorder: ObservableObject {
    @Published var recording = false
    @Published var requestingPermission = false
    @Published var output: URL?
    @Published var status = "Record your voice or import an audio file."
    private var recorder: AVAudioRecorder?
    private var timer: Task<Void, Never>?
    private var requestID = UUID()
    func start() async {
        guard !recording, !requestingPermission else { return }
        requestingPermission = true
        defer { requestingPermission = false }
        let request = UUID(); requestID = request
        let permitted = await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in AVAudioApplication.requestRecordPermission { c.resume(returning: $0) } }
        guard requestID == request else { return }
        guard permitted else { status = "Allow microphone access in iPhone Settings for VoiceMatrix, LiveContainer, or Strata."; return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker]); try session.setActive(true)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("Recording-\(UUID().uuidString).wav")
            let rec = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
            guard rec.record(forDuration: 10) else { throw StudioError.emptyAudio }
            TemporaryAudio.discard(output)
            recorder = rec; output = url; recording = true; status = "Recording… Tap Stop when finished. Maximum 10 seconds."
            timer = Task { try? await Task.sleep(nanoseconds: 10_000_000_000); if !Task.isCancelled { stop() } }
        } catch { status = "The microphone could not start. Check permission and available storage." }
    }
    func stop() {
        requestID = UUID()
        recorder?.stop(); recorder = nil; recording = false; timer?.cancel(); timer = nil
        guard let output, let file = try? AVAudioFile(forReading: output), file.length > 0 else { self.output = nil; status = "No audio was recorded. Try again."; return }
        status = "Your original recording is ready."
    }
    func discard() { stop(); TemporaryAudio.discard(output); output = nil }
    func importAudio(_ url: URL) {
        guard !recording else { return }
        let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
        do {
            let source = try AVAudioFile(forReading: url)
            guard source.length > 0, Double(source.length) / source.fileFormat.sampleRate <= 10.01 else { status = "Choose an audio file up to 10 seconds long."; return }
            let target = FileManager.default.temporaryDirectory.appendingPathComponent("Imported-\(UUID().uuidString).wav")
            var writer: AVAudioFile? = try AVAudioFile(forWriting: target, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: source.processingFormat.sampleRate, AVNumberOfChannelsKey: Int(source.processingFormat.channelCount), AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
            guard let buffer = AVAudioPCMBuffer(pcmFormat: source.processingFormat, frameCapacity: 8192) else { throw StudioError.emptyAudio }
            do {
                while source.framePosition < source.length { try source.read(into: buffer); try writer?.write(from: buffer) }
                writer = nil
            } catch { writer = nil; try? FileManager.default.removeItem(at: target); throw error }
            TemporaryAudio.discard(output)
            output = target; status = "Your original audio is ready."
        } catch { status = "That file could not be opened. Try a WAV, M4A, or CAF file." }
    }
}
struct RecordingView: View {
    @StateObject private var recorder = Recorder()
    @EnvironmentObject var audio: AudioStore
    @EnvironmentObject var studio: SpeechStudio
    @State private var importing = false
    @State private var choosing = false
    var body: some View {
        Form {
            Section("Step 1 · Record your voice") {
                Button {
                    audio.stop()
                    if recorder.recording { recorder.stop() } else { Task { await recorder.start() } }
                } label: { Label(recorder.recording ? "STOP RECORDING" : "RECORD MY VOICE", systemImage: recorder.recording ? "stop.fill" : "mic.fill").frame(minHeight: 52) }
                    .buttonStyle(.borderedProminent).disabled(studio.busy || recorder.requestingPermission)
                Button("Import Audio") { importing = true }.disabled(recorder.recording || recorder.requestingPermission || studio.busy)
                Text("Use a clear recording up to 10 seconds long.").font(.caption)
                Text(recorder.status)
            }
            Section("Step 2 · Choose a voice") {
                Button { choosing = true } label: { Label(studio.selected?.name ?? "Choose a voice", systemImage: "person.wave.2.fill") }.disabled(studio.busy || recorder.recording)
                if let voice = studio.selected { Text(voice.description).font(.caption).foregroundStyle(.secondary) }
            }
            Section("Step 3 · Tap Convert") {
                Button {
                    if let source = recorder.output { studio.changeVoice(source: source, audio: audio) }
                } label: { Label("CONVERT", systemImage: "waveform").frame(maxWidth: .infinity, minHeight: 50).font(.title3.bold()) }.buttonStyle(.borderedProminent)
                    .disabled(studio.busy || recorder.recording || recorder.requestingPermission || recorder.output == nil || studio.selected == nil)
                if studio.changingVoice { ProgressView("Changing your voice…"); Button("Cancel", role: .cancel) { studio.cancel() } }
                Text(studio.status).accessibilityAddTraits(.updatesFrequently)
            }
            Section("Step 4 · Listen or Save") {
                if let url = studio.changedOutput { AudioActions(url: url) } else { Text("Your changed voice will appear here.").foregroundStyle(.secondary) }
            }
            if let url = recorder.output, !recorder.recording {
                DisclosureGroup("Original recording") { AudioActions(url: url) }.disabled(studio.busy)
            }
        }.navigationTitle("Change My Voice")
            .onChange(of: recorder.recording) { _, _ in studio.recordingInProgress = recorder.recording || recorder.requestingPermission }
            .onChange(of: recorder.requestingPermission) { _, _ in studio.recordingInProgress = recorder.recording || recorder.requestingPermission }
            .onDisappear {
                if studio.changingVoice { studio.cancel() }
                recorder.discard(); studio.recordingInProgress = false; studio.clearChangedVoice(); audio.stop()
            }
            .sheet(isPresented: $choosing) { NavigationStack { VoicesView(onChoose: { choosing = false }) } }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.wav, .mpeg4Audio, .audio]) { result in
                switch result { case .success(let url): recorder.importAudio(url); case .failure: recorder.status = "Import was cancelled or the file could not be opened." }
            }
    }
}
