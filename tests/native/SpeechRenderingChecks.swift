import Foundation
import AVFoundation

@main struct SpeechRenderingChecks {
    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("source.wav")
        let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 96000)!
        buffer.frameLength = 96000
        for i in 0..<96000 { buffer.floatChannelData![0][i] = Float(sin(Double(i) * 2 * .pi * 440 / 24000)) * 0.2 }
        var writer: AVAudioFile? = try AVAudioFile(forWriting: source, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        try writer!.write(from: buffer); writer = nil
        let original = try Data(contentsOf: source)
        func inspect(_ url: URL) throws -> (Double, Double, Double) {
            let f = try AVAudioFile(forReading: url)
            let b = AVAudioPCMBuffer(pcmFormat: f.processingFormat, frameCapacity: AVAudioFrameCount(f.length))!
            try f.read(into: b)
            let p = b.floatChannelData![0]
            let start = 12000, end = min(Int(b.frameLength) - 12000, 36000)
            precondition(end > start)
            var crossings = 0, energy = 0.0
            for i in start..<end {
                precondition(p[i].isFinite)
                if p[i-1] <= 0 && p[i] > 0 { crossings += 1 }
                energy += Double(p[i]) * Double(p[i])
            }
            return (Double(f.length) / 24000, Double(crossings) * 24000 / Double(end-start), sqrt(energy / Double(end-start)))
        }
        let normal = root.appendingPathComponent("normal.wav")
        try await SpeechRendering.render(source: source, destination: normal, controls: SpeechControls())
        let normalData = try Data(contentsOf: normal)
        precondition(normalData == original)
        for (name, controls, duration, frequency) in [
            ("fast", SpeechControls(speed: 2), 2.25, 440.0),
            ("slow", SpeechControls(speed: 0.5), 8.25, 440.0),
            ("higher", SpeechControls(pitch: 12), 4.25, 880.0),
            ("lower", SpeechControls(pitch: -12), 4.25, 220.0)
        ] {
            let output = root.appendingPathComponent(name + ".wav")
            try await SpeechRendering.render(source: source, destination: output, controls: controls)
            let actual = try inspect(output)
            precondition(abs(actual.0-duration) < 0.2, "Incorrect speed duration: \(actual)")
            precondition(abs(actual.1-frequency) < frequency * 0.08, "Incorrect pitch: \(actual)")
            precondition(actual.2 > 0.01)
            print(name, actual)
        }
        let quiet = root.appendingPathComponent("quiet.wav")
        try await SpeechRendering.render(source: source, destination: quiet, controls: SpeechControls(volume: 0.5))
        let quietStats = try inspect(quiet), normalStats = try inspect(normal)
        precondition(quietStats.2 < normalStats.2 * 0.65)
        let invalid = root.appendingPathComponent("invalid.wav")
        do { try await SpeechRendering.render(source: source, destination: invalid, controls: SpeechControls(speed: .nan)); fatalError("Invalid setting accepted") } catch is SpeechRenderError {}
        precondition(!FileManager.default.fileExists(atPath: invalid.path))
        let cancelled = root.appendingPathComponent("cancelled.wav")
        let job = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            try await SpeechRendering.render(source: source, destination: cancelled, controls: SpeechControls(speed: 0.5))
        }
        do { try await job.value; fatalError("Cancellation ignored") } catch is CancellationError {}
        precondition(!FileManager.default.fileExists(atPath: cancelled.path))
        let interrupted = root.appendingPathComponent("interrupted.wav")
        let active = Task { try await SpeechRendering.render(source: source, destination: interrupted, controls: SpeechControls(speed: 0.5)) }
        for _ in 0..<10000 {
            if FileManager.default.fileExists(atPath: interrupted.path) { break }
            await Task.yield()
        }
        active.cancel()
        do { try await active.value; fatalError("In-progress cancellation ignored") } catch is CancellationError {}
        precondition(!FileManager.default.fileExists(atPath: interrupted.path))
        let preserved = try Data(contentsOf: source)
        precondition(preserved == original)
        print("Offline speed, pitch, volume, default bytes, cancellation and reference preservation passed")
    }
}
