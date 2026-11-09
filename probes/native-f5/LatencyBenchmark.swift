import Foundation
import AVFoundation
import Metal
import CryptoKit
import Darwin

@main struct SpeechLatencyBenchmark {
    static func main() async throws {
        let args = CommandLine.arguments
        guard args.count == 5, let gpu = MTLCreateSystemDefaultDevice() else { throw NSError(domain: "SpeechLatency", code: 1) }
        let bundle = URL(fileURLWithPath: args[1]), collection = URL(fileURLWithPath: args[2]), output = URL(fileURLWithPath: args[3])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let store = CharacterFolderStore(root: output.appendingPathComponent("ImportedDiagnostic"))
        let profiles = try await store.importCollection(at: collection)
        guard profiles.count == 1, let profile = profiles.first else { throw NSError(domain: "SpeechLatency", code: 2) }
        let reference = try await store.referenceURL(id: profile.id)
        let engine = F5ReferenceEngine()
        let texts = ["Welcome to the voice studio.", "I found a strange device near the portal.", "Please close the window and bring the notebook."]
        var cases: [[String: Any]] = []
        for (index, text) in texts.enumerated() {
            await engine.unload()
            var baseline: [Float] = []
            for mode in ["reload", "reuse"] {
                if mode == "reuse" { await engine.finishRequest(keepWarm: true) }
                let start = ProcessInfo.processInfo.systemUptime
                try await engine.load(localBundle: bundle)
                let loaded = ProcessInfo.processInfo.systemUptime
                let destination = output.appendingPathComponent("\(mode)-\(index).wav")
                try await engine.speak(text: text, referenceAudio: reference, referenceText: profile.referenceText, destination: destination)
                let finished = ProcessInfo.processInfo.systemUptime
                let wav = try AVAudioFile(forReading: destination)
                guard let buffer = AVAudioPCMBuffer(pcmFormat: wav.processingFormat, frameCapacity: AVAudioFrameCount(wav.length)) else { throw NSError(domain: "SpeechLatency", code: 3) }
                try wav.read(into: buffer)
                guard let channel = buffer.floatChannelData?[0] else { throw NSError(domain: "SpeechLatency", code: 4) }
                let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
                guard samples.count > 2400, samples.allSatisfy({ $0.isFinite && abs($0) < 1 }) else { throw NSError(domain: "SpeechLatency", code: 5) }
                let rms = sqrt(samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count))
                guard rms > 0.0001 else { throw NSError(domain: "SpeechLatency", code: 6) }
                if mode == "reload" { baseline = samples }
                guard samples.count == baseline.count else { throw NSError(domain: "SpeechLatency", code: 7) }
                let maxDifference = zip(samples, baseline).reduce(Float(0)) { max($0, abs($1.0 - $1.1)) }
                var usage = rusage(); getrusage(RUSAGE_SELF, &usage)
                let row: [String: Any] = ["case":index, "mode":mode, "loadSeconds":loaded-start, "synthesisSeconds":finished-loaded, "totalSeconds":finished-start, "audioSeconds":Double(wav.length)/wav.fileFormat.sampleRate, "rms":rms, "maxPCMDifferenceFromReload":maxDifference, "peakRSSBytes":usage.ru_maxrss, "file":destination.lastPathComponent, "sha256":SHA256.hash(data: try Data(contentsOf: destination)).map { String(format: "%02x", $0) }.joined()]
                cases.append(row)
                let report: [String: Any] = ["device":gpu.name, "steps":32, "seed":0, "networkDenied":true, "physicalIPhoneVerified":false, "cases":cases]
                try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys,.prettyPrinted]).write(to: URL(fileURLWithPath: args[4]), options: .atomic)
                print(String(data: try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]), encoding: .utf8)!)
            }
        }
        await engine.unload()
    }
}
