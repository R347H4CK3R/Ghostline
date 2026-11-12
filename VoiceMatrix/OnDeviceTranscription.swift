import Foundation
import Speech

/// Never falls back to server recognition. Missing local language support is explicit.
@MainActor final class OnDeviceTranscription {
    enum Failure: LocalizedError {
        case permission, unavailable, busy, noSpeech, timeout
        var errorDescription: String? {
            switch self {
            case .permission: return "Allow Speech Recognition in iPhone Settings to transcribe this local reference."
            case .unavailable: return "English on-device speech recognition is unavailable on this iPhone. No audio was sent to a server."
            case .busy: return "A local transcription is already running."
            case .noSpeech: return "No sufficiently confident speech transcript was found in this window."
            case .timeout: return "On-device transcription stopped after 45 seconds without a final result."
            }
        }
    }
    private var recognizer: SFSpeechRecognizer?
    private var task: SFSpeechRecognitionTask?
    private var deadline: Task<Void, Never>?
    private var continuation: CheckedContinuation<String, Error>?
    private var token: UUID?

    func authorize() async throws {
        let status: SFSpeechRecognizerAuthorizationStatus
        if SFSpeechRecognizer.authorizationStatus() == .notDetermined {
            status = await withCheckedContinuation { reply in SFSpeechRecognizer.requestAuthorization { reply.resume(returning: $0) } }
        } else { status = SFSpeechRecognizer.authorizationStatus() }
        try Task.checkCancellation()
        guard status == .authorized else { throw Failure.permission }
    }
    func transcribe(_ file: URL, activity: @escaping @MainActor () -> Void = {}) async throws -> String {
        try Task.checkCancellation()
        guard file.isFileURL else { throw Failure.unavailable }
        guard continuation == nil else { throw Failure.busy }
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else { throw Failure.permission }
        guard let engine = SFSpeechRecognizer(locale: Locale(identifier: "en-US")), engine.supportsOnDeviceRecognition, engine.isAvailable else { throw Failure.unavailable }
        let request = SFSpeechURLRecognitionRequest(url: file)
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        let run = UUID()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { reply in
                token = run; continuation = reply; recognizer = engine
                task = engine.recognitionTask(with: request) { [weak self] result, error in
                    Task { @MainActor in
                        guard let self, self.token == run else { return }
                        if let result {
                            activity()
                            if result.isFinal {
                                let segments = result.bestTranscription.segments
                                let text = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                                let confidence = segments.map(\.confidence).reduce(0, +) / Float(max(1, segments.count))
                                if LocalStudioEvidence.usableTranscript(text), confidence >= 0.35 { self.finish(run, .success(text)) }
                                else { self.finish(run, .failure(Failure.noSpeech)) }
                                return
                            }
                        }
                        if error != nil { self.finish(run, .failure(Failure.unavailable)) }
                    }
                }
                deadline = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(45)) } catch { return }
                    self?.finish(run, .failure(Failure.timeout))
                }
                if Task.isCancelled { finish(run, .failure(CancellationError())) }
            }
        } onCancel: { [weak self] in Task { @MainActor in self?.finish(run, .failure(CancellationError())) } }
    }
    private func finish(_ run: UUID, _ result: Result<String, Error>) {
        guard token == run, let reply = continuation else { return }
        continuation = nil; token = nil
        deadline?.cancel(); deadline = nil
        task?.cancel(); task = nil; recognizer = nil
        reply.resume(with: result)
    }
}
