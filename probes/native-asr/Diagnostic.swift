import Foundation
import CryptoKit

/// Real recognition using the exact production wrapper. Only the two pre-pinned
/// neutral synthetic WAVs are accepted. No downloaded/private audio or stubs.
@main struct BundledASRDiagnostic {
    struct Result: Codable { let file, sha256, expected, recognized: String; let wordErrorRate: Double; let transcriptionEvidence: OnDeviceTranscription.Evidence }
    struct Evidence: Codable {
        let schemaVersion = 1
        let modelRevision = BundledASRAssets.revision
        let resourceLockSHA256 = BundledASRAssets.lockSHA256
        let engine = "FluidAudio ee78635d23d52379117554ba72358b65a0612447 / Parakeet v3 Encoder_v2"
        let sourceCommit: String
        let results: [Result]
        let cancelledRequestRejected: Bool
        let retryAfterCancellationPassed: Bool
        let fullLocalPipelineVerified = false
        let physicalDeviceVerified = false
    }
    enum Failure: Error { case arguments, fixture, words, cancellation }
    @MainActor static func main() async throws {
        guard CommandLine.arguments.count == 5 else { throw Failure.arguments }
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let fixtures = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        let output = URL(fileURLWithPath: CommandLine.arguments[3])
        let commit = CommandLine.arguments[4]
        guard commit.range(of: "^[a-f0-9]{40}$", options: .regularExpression) != nil else { throw Failure.arguments }
        let records = [
            ("conversion-source.wav", 108032, "8741b5ebb943f4c39006b6c7a7dd5ca92f344edb402744ad7132ee1f94ff45b4", "I found a strange device near the portal."),
            ("conversion-reference.wav", 123392, "0840a3b08d2d438804e760afa54bc1c9cdf1c8b33bffdc1ab458be4ab3740cd2", "Please close the window and bring the notebook.")
        ]
        for (name, size, digest, _) in records {
            let url = fixtures.appendingPathComponent(name)
            let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == size else { throw Failure.fixture }
            let data = try Data(contentsOf: url)
            guard SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == digest else { throw Failure.fixture }
        }
        let transcriber = OnDeviceTranscription(bundle: root)
        try await transcriber.authorize()
        // Cancel an admitted request at an implementation-defined safe boundary.
        // This is not proof that CoreML itself can be preempted mid-prediction.
        let cancelled = Task { try await transcriber.transcribe(fixtures.appendingPathComponent(records[0].0)) }
        try await Task.sleep(for: .milliseconds(20)); cancelled.cancel()
        do { _ = try await cancelled.value; throw Failure.cancellation }
        catch is CancellationError { }
        var results: [Result] = []
        for (name, _, digest, expected) in records {
            let text = try await transcriber.transcribe(fixtures.appendingPathComponent(name))
            let wer = LocalStudioEvidence.wordErrorRate(expected: expected, actual: text)
            guard wer <= 0.1 else { throw Failure.words }
            guard let detail = transcriber.lastEvidence, detail.inputSHA256 == digest else { throw Failure.fixture }
            results.append(Result(file: name, sha256: digest, expected: expected, recognized: text, wordErrorRate: wer, transcriptionEvidence: detail))
        }
        let evidence = Evidence(sourceCommit: commit, results: results, cancelledRequestRejected: true, retryAfterCancellationPassed: true)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(evidence).write(to: output, options: .atomic)
        print("Real bundled ASR fixture checks passed; full local pipeline and physical device remain unverified")
    }
}
