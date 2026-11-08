import Foundation
import AVFoundation
import F5TTS

// Isolated API/compile probe; no bundled character assets or runtime verification claimed.
actor F5ReferenceEngine {
    private var engine: F5TTSModel?
    func load(localBundle: URL) async throws {
        try Task.checkCancellation()
        engine = try await F5TTSModel.fromBundle(localBundle)
    }
    func speak(text: String, referenceAudio: URL, referenceText: String, destination: URL) async throws {
        guard let engine, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !referenceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw NSError(domain: "VoiceMatrix.F5", code: 1, userInfo: [NSLocalizedDescriptionKey: "Load a local engine and character reference first."])
        }
        try Task.checkCancellation()
        let samples = try await engine.generate(text: text, referenceAudio: referenceAudio, referenceText: referenceText)
        try Task.checkCancellation()
        guard samples.count >= 2400, samples.allSatisfy({ $0.isFinite }),
              samples.reduce(0.0, { $0 + Double($1) * Double($1) }) / Double(samples.count) > 1e-8,
              let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let channel = buffer.floatChannelData?[0] else {
            throw NSError(domain: "VoiceMatrix.F5", code: 2, userInfo: [NSLocalizedDescriptionKey: "The voice did not produce usable speech."])
        }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        let gain = min(1, 0.98 / max(samples.map { abs($0) }.max() ?? 0, 0.000001))
        for (index, value) in samples.enumerated() { channel[index] = value * gain }
        let writer = try AVAudioFile(forWriting: destination, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        try writer.write(from: buffer)
    }
}
