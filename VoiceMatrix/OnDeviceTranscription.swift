import Foundation
import AVFoundation
import CryptoKit
@preconcurrency import CoreML
import FluidAudio

/// Bundled ASR only. No OS speech permission/assets, service, downloader or purge.
/// Each call owns and releases its models before returning, including on cancellation.
@MainActor final class OnDeviceTranscription {
    enum Failure: LocalizedError {
        case unavailable, busy, noSpeech, timeout, invalidAudio
        var errorDescription: String? {
            switch self {
            case .unavailable: return "Bundled speech recognition could not finish. Source and existing voices were retained; no server fallback was used."
            case .busy: return "A local transcription is already running."
            case .noSpeech: return "No usable speech transcript was found in this window."
            case .timeout: return "Speech recognition exceeded 45 seconds and was stopped at a safe model boundary. Retained media was kept."
            case .invalidAudio: return "Local transcription requires a mono WAV of 0.2–30 seconds, at 16–48 kHz, no larger than 8 MiB."
            }
        }
    }
    struct Evidence: Codable, Sendable {
        let schemaVersion = 1
        let modelRevision = BundledASRAssets.revision
        let inputSHA256, transcriptSHA256: String
        let tokenCount: Int
        let meanTokenConfidence: Float
        let confidenceMeaning = "Uncalibrated mean token softmax, not transcript accuracy"
    }
    private(set) var lastEvidence: Evidence?
    private let bundle: URL?
    private var token: UUID?
    private var deadlineExpired = false
    init(bundle: URL? = Bundle.main.url(forResource: "ParakeetASR", withExtension: nil)) { self.bundle = bundle }

    /// Preserve the caller interface, but do not ask for OS speech authorization.
    /// This verifies the small pinned manifest, without loading model weights.
    func authorize() async throws {
        try Task.checkCancellation()
        guard let bundle else { throw BundledASRAssets.Failure.missing }
        do { _ = try BundledASRAssets.manifest(at: bundle) }
        catch is CancellationError { throw CancellationError() }
        catch { throw BundledASRAssets.Failure.invalid }
    }
    func transcribe(_ file: URL, activity: @escaping @MainActor () -> Void = {}) async throws -> String {
        try Task.checkCancellation()
        guard token == nil else { throw Failure.busy }
        guard let bundle else { throw BundledASRAssets.Failure.missing }
        let run = UUID(); token = run; deadlineExpired = false; lastEvidence = nil
        let worker = Task.detached(priority: .userInitiated) { try await Self.recognize(file, bundle: bundle) }
        let deadline = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(45)) } catch { return }
            guard let self, self.token == run else { return }
            self.deadlineExpired = true; worker.cancel()
        }
        defer { deadline.cancel(); token = nil }
        do {
            let (text, evidence) = try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
            try Task.checkCancellation()
            if deadlineExpired { throw Failure.timeout }
            lastEvidence = evidence
            activity() // A real final result, never a timer-based progress claim.
            return text
        } catch {
            if Task.isCancelled { throw CancellationError() }
            if deadlineExpired { throw Failure.timeout }
            if error is Failure || error is BundledASRAssets.Failure { throw error }
            throw Failure.unavailable
        }
    }
    private nonisolated static func recognize(_ file: URL, bundle: URL) async throws -> (String, Evidence) {
        try Task.checkCancellation()
        guard file.isFileURL, file.pathExtension.lowercased() == "wav" else { throw Failure.invalidAudio }
        let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, (44...8_388_608).contains(size) else { throw Failure.invalidAudio }
        let audio = try AVAudioFile(forReading: file)
        let rate = audio.processingFormat.sampleRate
        let seconds = Double(audio.length) / rate
        guard rate.isFinite, (16_000...48_000).contains(rate), audio.processingFormat.channelCount == 1,
              seconds.isFinite, (0.2...30).contains(seconds) else { throw Failure.invalidAudio }
        let inputSHA256 = try inputDigest(file, byteCount: size)
        try BundledASRAssets.verify(bundle)
        try Task.checkCancellation()
        let config = MLModelConfiguration(); config.computeUnits = .cpuAndNeuralEngine
        // Explicitly select the larger rebuilt encoder. Pinned SDK documents
        // right-context token corruption in the original 6-bit Encoder.mlmodelc.
        let manager = AsrManager(config: ASRConfig(parallelChunkConcurrency: 1), models:
            try AsrModels.loadLocal(from: bundle, version: .v3, configuration: config,
                                    encoderPrecision: .int8V2, encoderComputeUnits: .cpuAndNeuralEngine))
        do {
            try Task.checkCancellation()
            var decoder = try TdtDecoderState(decoderLayers: 2)
            let result = try await manager.transcribe(file, decoderState: &decoder)
            try Task.checkCancellation()
            let text = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
            // Do not use result.confidence: pinned SDK substitutes 0.5 if scores
            // are absent. tokenTimings exists only when actual per-token scores match.
            guard LocalStudioEvidence.usableTranscript(text), let timings = result.tokenTimings,
                  let mean = BundledASRPolicy.admittedTokenMean(timings.map(\.confidence)) else { throw Failure.noSpeech }
            // FluidAudio reopens the pathname. Reject changes before publishing
            // evidence, rather than attaching the earlier hash to different audio.
            _ = try inputDigest(file, byteCount: size, matching: inputSHA256)
            let evidence = Evidence(inputSHA256: inputSHA256,
                transcriptSHA256: SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined(),
                tokenCount: timings.count, meanTokenConfidence: mean)
            await manager.cleanup()
            return (text, evidence)
        } catch {
            await manager.cleanup()
            throw error
        }
    }
    nonisolated static func inputDigest(_ file: URL, byteCount: Int, matching: String? = nil) throws -> String {
        try Task.checkCancellation()
        guard file.isFileURL, (1...8_388_608).contains(byteCount) else { throw Failure.invalidAudio }
        let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == byteCount else { throw Failure.invalidAudio }
        let handle = try FileHandle(forReadingFrom: file); defer { try? handle.close() }
        var hash = SHA256(), count = 0
        while let bytes = try handle.read(upToCount: 1_048_576), !bytes.isEmpty {
            try Task.checkCancellation(); count += bytes.count
            guard count <= byteCount else { throw Failure.invalidAudio }
            hash.update(data: bytes)
        }
        let digest = hash.finalize().map { String(format: "%02x", $0) }.joined()
        guard count == byteCount, matching == nil || matching == digest else { throw Failure.invalidAudio }
        return digest
    }

}
