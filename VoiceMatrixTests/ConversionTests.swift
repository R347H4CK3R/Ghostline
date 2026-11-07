import XCTest
import Foundation
import AVFoundation
@testable import VoiceMatrix

final class ConversionTests: XCTestCase {
    private struct Golden: Decodable {
        struct Case: Decodable { struct Point: Decodable { let frame, bin: Int; let magnitude: Float }; let name: String; let points: [Point] }
        let sampleCount: Int
        let cases: [Case]
    }
    func testSTFTMatchesIndependentNumpyReferenceIncludingEndpoints() throws {
        let url = try XCTUnwrap(Bundle(for: ConversionTests.self).url(forResource: "stft-golden", withExtension: "json"))
        let golden = try JSONDecoder().decode(Golden.self, from: Data(contentsOf: url))
        for test in golden.cases {
            let samples: [Float] = (0..<golden.sampleCount).map { index in
                switch test.name {
                case "constant": return 0.25
                case "nyquist": return index % 2 == 0 ? 0.25 : -0.25
                default: return Float(0.2 * sin(2 * Double.pi * 440 * Double(index) / 22050) + 0.1 * sin(2 * Double.pi * 1100 * Double(index) / 22050))
                }
            }
            let actual = try ConversionAudio.spectrum(samples)
            XCTAssertEqual(actual.frames, 16)
            for p in test.points { XCTAssertEqual(actual.values[p.frame * 513 + p.bin], p.magnitude, accuracy: 0.003, "\(test.name) frame=\(p.frame) bin=\(p.bin)") }
        }
    }
    func testEmptyAndTooShortSpectraAreRejected() {
        XCTAssertThrowsError(try ConversionAudio.spectrum([]))
        XCTAssertThrowsError(try ConversionAudio.spectrum([0]))
    }
    func testExportPreventsClippingWithGainInsteadOfFlatteningPeaks() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: url) }
        let samples = (0..<22050).map { Float(2 * sin(Double($0) * 0.1)) }
        try ConversionAudio.write(samples, to: url)
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)))
        try file.read(into: buffer)
        let data = try XCTUnwrap(buffer.floatChannelData?[0])
        let output = Array(UnsafeBufferPointer(start: data, count: Int(buffer.frameLength)))
        XCTAssertGreaterThan(output.max() ?? 0, 0.97)
        XCTAssertLessThan(output.max() ?? 1, 0.981)
        XCTAssertTrue(output.allSatisfy { abs($0) < 0.981 })
        XCTAssertGreaterThan(Set(output.map { Int($0 * 1000) }).count, 100)
    }
    func testStereoResamplingPreservesFullThreeSecondRecording() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: url) }
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 2))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 72000))
        buffer.frameLength = 72000
        let channels = try XCTUnwrap(buffer.floatChannelData)
        for index in 0..<72000 {
            let sample = Float(0.2 * sin(2 * Double.pi * 440 * Double(index) / 24000))
            channels[0][index] = sample; channels[1][index] = sample
        }
        var file: AVAudioFile? = try AVAudioFile(forWriting: url, settings: format.settings)
        try file?.write(from: buffer); file = nil
        let samples = try ConversionAudio.readMono(url)
        XCTAssertEqual(Double(samples.count), 66150, accuracy: 64)
        XCTAssertTrue(samples.allSatisfy(\.isFinite))
        let rms = sqrt(samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count))
        XCTAssertEqual(rms, 0.2 / sqrt(2.0), accuracy: 0.005)
    }
    func testActualOfflineToneConversionPreservesDurationAndMovesTowardTarget() async throws {
        executionTimeAllowance = 600
        let (root, manifest) = try Catalog.read()
        let sourceVoice = try XCTUnwrap(manifest.voices.first { $0.id == "en_us_Micah" })
        let targetVoice = try XCTUnwrap(manifest.voices.first { $0.id == "en_us_Zoey" })
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("VoiceMatrix-Conversion-QA")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let source = folder.appendingPathComponent("source.wav")
        let reference = folder.appendingPathComponent("target-reference.wav")
        let output = folder.appendingPathComponent("converted.wav")
        let speech = NeuralSpeech(computeUnits: .cpuOnly)
        _ = try await speech.generate(text: "Please bring three blue notebooks to the quiet room before lunch.", voice: sourceVoice, root: root, manifest: manifest, output: source)
        _ = try await speech.generate(text: "Welcome to the studio. Today we are testing a different voice.", voice: targetVoice, root: root, manifest: manifest, output: reference)
        await speech.unload()
        let converter = OfflineVoiceConverter(computeUnits: .cpuOnly)
        let target = try await converter.extractEmbedding(from: reference)
        let result = try await converter.convert(source: source, target: target, destination: output)
        XCTAssertEqual(result.sourceSeconds, result.outputSeconds, accuracy: 0.04)
        let converted = try await converter.extractEmbedding(from: output)
        let before = OfflineVoiceConverter.cosine(result.sourceEmbedding, target)
        let after = OfflineVoiceConverter.cosine(converted, target)
        print("VoiceMatrix conversion probe targetCosineBefore=\(before) targetCosineAfter=\(after) duration=\(result.outputSeconds)")
        XCTAssertGreaterThan(after, before + 0.02, "The converter must measurably move the speaker conditioning toward the selected target")
        for file in [source, reference, output] {
            let attachment = XCTAttachment(contentsOfFile: file)
            attachment.name = file.lastPathComponent; attachment.lifetime = .keepAlways; add(attachment)
        }
        await converter.unload()
    }

}
