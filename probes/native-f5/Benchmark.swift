import Foundation
import AVFoundation
import Metal
import Darwin

@main struct NativeF5Benchmark {
    static func main() async throws {
        guard CommandLine.arguments.count == 5, let gpu = MTLCreateSystemDefaultDevice() else {
            throw NSError(domain: "VoiceMatrix.Benchmark", code: 1, userInfo: [NSLocalizedDescriptionKey: "A Metal-capable Apple runner and local bundle/reference/output/report paths are required."])
        }
        let args = CommandLine.arguments
        let engine = F5ReferenceEngine()
        let loadStart = Date()
        try await engine.load(localBundle: URL(fileURLWithPath: args[1]))
        let loadSeconds = Date().timeIntervalSince(loadStart)
        let started = Date()
        let destination = URL(fileURLWithPath: args[3])
        try await engine.speak(text: "Welcome to the voice studio.", referenceAudio: URL(fileURLWithPath: args[2]), referenceText: "This is a clear reference recording. Today we are checking an offline speech engine.", destination: destination)
        let elapsed = Date().timeIntervalSince(started)
        let file = try AVAudioFile(forReading: destination)
        guard let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)) else { throw NSError(domain: "VoiceMatrix.Benchmark", code: 2) }
        try file.read(into: buffer)
        guard buffer.frameLength > 2400, let channel = buffer.floatChannelData?[0] else { throw NSError(domain: "VoiceMatrix.Benchmark", code: 3) }
        let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
        let energy = samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count)
        guard samples.allSatisfy({ $0.isFinite && abs($0) < 1 }), energy > 1e-8 else { throw NSError(domain: "VoiceMatrix.Benchmark", code: 4) }
        var usage = rusage()
        getrusage(RUSAGE_SELF, &usage)
        let report: [String: Any] = ["engine":"F5TTS_v1_Base", "runtimeRevision":"a57702e6f523fa36ac5532d2bdc5f35f701a052c", "device":gpu.name, "loadSeconds":loadSeconds, "synthesisSeconds":elapsed, "audioSeconds":Double(file.length)/file.fileFormat.sampleRate, "rms":sqrt(energy), "peakRSSBytes":usage.ru_maxrss, "decodedNonSilentWAV":true, "networkDeniedBySandbox":true, "physicalIPhoneVerified":false, "likenessVerified":false, "intelligibilityVerified":false, "reference":"macOS generated diagnostic reference; no character likeness asserted"]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: args[4]), options: .atomic)
    }
}
