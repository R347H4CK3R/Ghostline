import XCTest
import AVFoundation
import CryptoKit
@testable import VoiceMatrix

final class F5SimulatorTests: XCTestCase {
    func testActualLocalF5ProducesDecodableNonSilentAudio() async throws {
        executionTimeAllowance = 600
        let reference = try XCTUnwrap(Bundle(for: Self.self).url(forResource:"simulator-reference",withExtension:"wav"))
        let model = try XCTUnwrap(Bundle.main.url(forResource:"F5TTS",withExtension:nil))
        let output = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at:output) }
        let engine = F5ReferenceEngine()
        let start = Date()
        try await engine.load(localBundle:model)
        let loaded = Date()
        try await engine.speak(text:"Please bring three blue notebooks.",referenceAudio:reference,referenceText:"The morning air is clear and the streets are quiet today.",destination:output)
        let generated = Date()
        let file = try AVAudioFile(forReading:output)
        XCTAssertEqual(file.fileFormat.sampleRate,24000)
        XCTAssertGreaterThan(file.length,2400)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat:file.processingFormat,frameCapacity:AVAudioFrameCount(file.length)))
        try file.read(into:buffer)
        let samples = try XCTUnwrap(buffer.floatChannelData)[0]
        var energy = 0.0
        for i in 0..<Int(buffer.frameLength) { XCTAssertTrue(samples[i].isFinite); energy += Double(samples[i]*samples[i]) }
        XCTAssertGreaterThan(energy / Double(buffer.frameLength),1e-8)
        let audio = XCTAttachment(contentsOfFile:output);audio.name="simulator-f5-output.wav";audio.lifetime = .keepAlways;add(audio)
        let input = XCTAttachment(contentsOfFile:reference);input.name="simulator-reference.wav";input.lifetime = .keepAlways;add(input)
        let report:[String:Any] = ["platform":"iOS Simulator","referenceSHA256":SHA256.hash(data:try Data(contentsOf:reference)).map { String(format:"%02x",$0) }.joined(),"outputSHA256":SHA256.hash(data:try Data(contentsOf:output)).map { String(format:"%02x",$0) }.joined(),"loadSeconds":loaded.timeIntervalSince(start),"generateSeconds":generated.timeIntervalSince(loaded),"audioSeconds":Double(file.length)/24000,"physicalIPhoneVerified":false,"characterLikenessVerified":false]
        let evidence = XCTAttachment(data:try JSONSerialization.data(withJSONObject:report,options:.prettyPrinted),uniformTypeIdentifier:"public.json"); evidence.name="simulator-f5-report.json";evidence.lifetime = .keepAlways;add(evidence)
        await engine.unload()
    }
}
