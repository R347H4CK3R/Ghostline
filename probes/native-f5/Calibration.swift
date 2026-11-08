import Foundation
import AVFoundation
import Metal
import CryptoKit
import Darwin

@main struct NativeF5Calibration {
    static func main() async throws {
        let args = CommandLine.arguments
        guard args.count == 5, let gpu = MTLCreateSystemDefaultDevice() else { throw NSError(domain: "Calibration", code: 1) }
        let bundle = URL(fileURLWithPath: args[1]), reference = URL(fileURLWithPath: args[2]), output = URL(fileURLWithPath: args[3])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let referenceText = "This is a clear reference recording. Today we are checking an offline speech engine."
        let texts = ["Welcome to the voice studio.", "I found a strange device near the portal.", "Please close the window and bring the notebook."]
        var cases: [[String: Any]] = []
        for (steps, seed) in [(16, UInt64(0)), (16, UInt64(347)), (32, UInt64(0)), (32, UInt64(347))] {
            let engine = F5ReferenceEngine(steps: steps, seed: seed)
            try await engine.load(localBundle: bundle)
            for (index, text) in texts.enumerated() {
                let identifier = "steps\(steps)-seed\(seed)-case\(index)"
                let destination = output.appendingPathComponent(identifier + ".wav")
                let start = Date()
                var row: [String: Any] = ["id":identifier, "configuration":"steps\(steps)-seed\(seed)", "steps":steps, "seed":seed, "expectedText":text, "file":destination.lastPathComponent]
                do {
                    try await engine.speak(text: text, referenceAudio: reference, referenceText: referenceText, destination: destination)
                    let wav = try AVAudioFile(forReading: destination)
                    row["generatedWAVSHA256"] = SHA256.hash(data: try Data(contentsOf: destination)).map { String(format: "%02x", $0) }.joined()
                    row["audioSeconds"] = Double(wav.length) / wav.fileFormat.sampleRate
                    row["status"] = "generated-needs-independent-wordcheck"
                } catch { row["status"] = "generation-failed"; row["reason"] = error.localizedDescription }
                row["synthesisSeconds"] = Date().timeIntervalSince(start)
                cases.append(row)
                let report: [String: Any] = ["engine":"F5TTS_v1_Base", "runtimeRevision":"a57702e6f523fa36ac5532d2bdc5f35f701a052c", "adapterSource":"VoiceMatrix/F5ReferenceEngine.swift", "device":gpu.name, "networkDeniedBySandbox":true, "physicalIPhoneVerified":false, "likenessVerified":false, "referenceKind":"macOS diagnostic synthetic speech", "cases":cases]
                try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys,.prettyPrinted]).write(to: URL(fileURLWithPath: args[4]), options: .atomic)
            }
            await engine.unload()
        }
    }
}
