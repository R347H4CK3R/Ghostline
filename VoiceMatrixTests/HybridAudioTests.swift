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

}
