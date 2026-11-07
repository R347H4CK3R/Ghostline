import XCTest
import AVFoundation
@testable import VoiceMatrix
final class HybridAudioTests: XCTestCase {
    func testChunkingPreservesWordsAndSentenceBoundaries() {
        let text = "Hello, this is a test. Please bring three blue notebooks to the quiet room before lunch."
        let chunks = SpeechTextChunks.split(text)
        XCTAssertEqual(chunks.joined(separator: " "), text)
        XCTAssertEqual(chunks.first, "Hello, this is a test.")
        XCTAssertTrue(chunks.allSatisfy { $0.split(whereSeparator: \.isWhitespace).count <= 12 })
    }
    func testLongInputHasNoMissingOrRepeatedWords() {
        let words = (0..<400).map { "word\($0)" }
        let chunks = SpeechTextChunks.split(words.joined(separator: " "))
        XCTAssertEqual(chunks.flatMap { $0.split(whereSeparator: \.isWhitespace).map(String.init) }, words)
        XCTAssertTrue(SpeechTextChunks.split(" \n ").isEmpty)
    }
    func testCombiningConvertedChunksPreservesSamplesAndValidWAV() throws {
        let root = FileManager.default.temporaryDirectory
        let first = root.appendingPathComponent(UUID().uuidString+".wav")
        let second = root.appendingPathComponent(UUID().uuidString+".wav")
        let output = root.appendingPathComponent(UUID().uuidString+".wav")
        defer { for url in [first, second, output] { try? FileManager.default.removeItem(at: url) } }
        try ConversionAudio.write((0..<22050).map { Float(sin(Double($0) * 0.1)) * 0.2 }, to: first)
        try ConversionAudio.write((0..<11025).map { Float(sin(Double($0) * 0.2)) * 0.1 }, to: second)
        let duration = try ConvertedAudioAssembler.join([first,second], to: output)
        XCTAssertEqual(duration, 1.5, accuracy: 0.0001)
        let file = try AVAudioFile(forReading: output)
        XCTAssertEqual(file.length, 33075)
        XCTAssertEqual(file.fileFormat.sampleRate, 22050)
    }
    func testCompactConditioningRoundTripPreservesHalfPrecisionValues() throws {
        let vector = (0..<256).map { Float(Float16(Float($0 - 128) / 127)) }
        let profile = ConversionProfile(id: "original", ttsEmbeddingSHA256: "base", converterRevision: "pinned", referenceAudioSHA256: "reference", embedding: vector)
        let data = try JSONEncoder().encode(profile)
        XCTAssertLessThan(data.count, 1100)
        let decoded = try JSONDecoder().decode(ConversionProfile.self, from: data)
        XCTAssertEqual(decoded.embedding, vector)
    }

    func testIntegratedConditionedVoiceHandlesMoreThanOneTextChunk() async throws {
        let (root, manifest) = try Catalog.read()
        let voice = try XCTUnwrap(manifest.voices.first { $0.engine == "phonon31m-openvoicev2" })
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-\(UUID().uuidString).wav")
        defer { TemporaryAudio.discard(output) }
        let engine = NeuralSpeech(computeUnits: .cpuOnly)
        let duration = try await engine.generate(text: "Please bring three blue notebooks to the quiet room before lunch. After lunch, we will read a longer story together and listen to every word.", voice: voice, root: root, manifest: manifest, output: output)
        XCTAssertGreaterThan(duration, 5)
        let file = try AVAudioFile(forReading: output)
        XCTAssertEqual(file.fileFormat.sampleRate, 22050)
        XCTAssertEqual(Double(file.length) / 22050, duration, accuracy: 0.001)
        await engine.unload()
    }
    func testCancellationBeforeGenerationCreatesNoAudio() async throws {
        let (root, manifest) = try Catalog.read()
        let voice = try XCTUnwrap(manifest.voices.first)
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-\(UUID().uuidString).wav")
        let engine = NeuralSpeech(computeUnits: .cpuOnly)
        let work = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await engine.generate(text: "This must stop.", voice: voice, root: root, manifest: manifest, output: output)
        }
        do { _ = try await work.value; XCTFail("Canceled generation must not succeed") }
        catch is CancellationError { }
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
    }

}
