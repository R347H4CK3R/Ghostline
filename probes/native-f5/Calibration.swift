import Foundation
import AVFoundation
import Metal
import CryptoKit
import Darwin

@main struct NativeF5Calibration {
    static func main() async throws {
        let args = CommandLine.arguments
        guard args.count == 5, let gpu = MTLCreateSystemDefaultDevice() else { throw NSError(domain: "Calibration", code: 1) }
        let bundle = URL(fileURLWithPath: args[1]), collection = URL(fileURLWithPath: args[2]), output = URL(fileURLWithPath: args[3])
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let store = CharacterFolderStore(root: output.appendingPathComponent("ImportedDiagnostic"))
        let profiles = try await store.importCollection(at: collection)
        guard profiles.count == 1, let profile = profiles.first, profile.id == "diagnostic-neutral" else { throw NSError(domain: "DiagnosticImport", code: 1) }
        let reference = try await store.referenceURL(id: profile.id)
        let referenceText = profile.referenceText
        let texts = ["Welcome to the voice studio.", "I found a strange device near the portal.", "Please close the window and bring the notebook."]
        var cases: [[String: Any]] = []
        for (steps, seed) in [(16, UInt64(0)), (16, UInt64(347)), (32, UInt64(0)), (32, UInt64(347))] {
            let engine = F5ReferenceEngine(steps: steps, seed: seed)
            try await engine.load(localBundle: bundle)
            var requested = texts
            if steps == 32 && seed == 0 {
                requested.append("Please open the blue notebook and write down these instructions. First close the window and put the book on the table. Then bring a glass of water to the quiet room. We will check every sentence before saving the recording. Keep the door open until everyone has arrived. After the test is finished, return the notebook to the desk and turn off the light. Keep a second copy of these notes and check the date before leaving the room.")
            }
            for (index, text) in requested.enumerated() {
                let identifier = "steps\(steps)-seed\(seed)-case\(index)"
                let destination = output.appendingPathComponent(identifier + ".wav")
                let input = try AVAudioFile(forReading: reference)
                let chunkCount = try F5SpeechChunks.plan(text: text, referenceText: referenceText, referenceSeconds: Double(input.length) / input.fileFormat.sampleRate).count
                if index == 3 { guard chunkCount > 1 else { throw NSError(domain: "ExpectedChunkedDiagnostic", code: 1) } }
                let start = Date()
                var row: [String: Any] = ["id":identifier, "configuration":"steps\(steps)-seed\(seed)", "steps":steps, "seed":seed, "chunkCount":chunkCount, "longMessage":index == 3, "expectedText":text, "file":destination.lastPathComponent]
                do {
                    try await engine.speak(text: text, referenceAudio: reference, referenceText: referenceText, destination: destination)
                    let wav = try AVAudioFile(forReading: destination)
                    row["generatedWAVSHA256"] = SHA256.hash(data: try Data(contentsOf: destination)).map { String(format: "%02x", $0) }.joined()
                    row["audioSeconds"] = Double(wav.length) / wav.fileFormat.sampleRate
                    row["status"] = "generated-needs-independent-wordcheck"
                } catch { row["status"] = "generation-failed"; row["reason"] = error.localizedDescription }
                row["synthesisSeconds"] = Date().timeIntervalSince(start)
                cases.append(row)
                let report: [String: Any] = ["engine":"F5TTS_v1_Base", "runtimeRevision":"a57702e6f523fa36ac5532d2bdc5f35f701a052c", "adapterSource":"VoiceMatrix/F5ReferenceEngine.swift", "importedProfileID":profile.id, "importedProfileCount":profiles.count, "engineProofSHA256":SHA256.hash(data: try Data(contentsOf: bundle.appendingPathComponent("voicematrix-engine.json"))).map { String(format: "%02x", $0) }.joined(), "device":gpu.name, "networkDeniedBySandbox":true, "physicalIPhoneVerified":false, "likenessVerified":false, "referenceKind":"pinned neutral synthetic speech fixture", "referenceAudioSHA256":SHA256.hash(data: try Data(contentsOf: reference)).map { String(format: "%02x", $0) }.joined(), "cases":cases]
                try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys,.prettyPrinted]).write(to: URL(fileURLWithPath: args[4]), options: .atomic)
            }
            await engine.unload()
        }
    }
}
