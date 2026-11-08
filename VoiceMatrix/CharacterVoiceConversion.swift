import Foundation

// One local shared encoder/converter, conditioned by the selected private reference.
// This is neural speech-to-speech conversion, not transcription followed by speech.
actor CharacterVoiceConversion {
    private let converter = OfflineVoiceConverter()
    private var running = false
    func run(reference: URL, source: URL, destination: URL, progress: @escaping @Sendable (String) -> Void = { _ in }) async throws -> ConversionResult {
        guard !running else { throw StudioError.busy }
        running = true
        defer { running = false }
        do {
            try Task.checkCancellation()
            progress("Preparing the selected character")
            let target = try await converter.extractEmbedding(from: reference)
            try Task.checkCancellation()
            let result = try await converter.convert(source: source, target: target, destination: destination, progress: progress)
            try Task.checkCancellation()
            await converter.unload()
            return result
        } catch {
            await converter.unload()
            try? FileManager.default.removeItem(at: destination)
            throw error
        }
    }
}
