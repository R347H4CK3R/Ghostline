import XCTest
import AVFoundation
import CryptoKit
@testable import VoiceMatrix

final class ReferenceBankTests: XCTestCase {
    private struct Bank: Decodable {
        struct Reference: Decodable {
            let id, referenceFile, referenceSHA256, sourcePath: String
            let ttsBaseVoiceID: String
        }
        let profiles: [Reference]
    }
    func testEnrollAndRenderLicensedReferenceCandidates() async throws {
        executionTimeAllowance = 1200
        let bankRoot = try XCTUnwrap(Bundle.main.url(forResource: "ReferenceBank", withExtension: nil))
        let bank = try JSONDecoder().decode(Bank.self, from: Data(contentsOf: bankRoot.appendingPathComponent("reference-manifest.json")))
        XCTAssertFalse(bank.profiles.isEmpty)
        let (root, manifest) = try Catalog.read()
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("VoiceMatrix-Bank-QA")
        try FileManager.default.createDirectory(at: folder.appendingPathComponent("Profiles"), withIntermediateDirectories: true)
        let text = "Please bring three blue notebooks to the quiet room before lunch."
        let speech = NeuralSpeech(computeUnits: .cpuOnly)
        var sources: [String: URL] = [:]
        for id in ["en_us_Micah", "en_us_Zoey"] {
            let voice = try XCTUnwrap(manifest.voices.first { $0.id == id })
            let url = folder.appendingPathComponent(id).appendingPathExtension("wav")
            _ = try await speech.generate(text: text, voice: voice, root: root, manifest: manifest, output: url)
            sources[id] = url
        }
        await speech.unload()
        let converter = OfflineVoiceConverter(computeUnits: .cpuOnly)
        let revision = try await converter.sourceRevision()
        var targets: [String: [Float]] = [:]
        var records: [String: [String: Any]] = [:]
        for reference in bank.profiles {
            let url = bankRoot.appendingPathComponent(reference.referenceFile)
            let hash = SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
            XCTAssertEqual(hash, reference.referenceSHA256)
            do {
                let embedding = try await converter.extractEmbedding(from: url)
                let base = try XCTUnwrap(manifest.voices.first { $0.id == reference.ttsBaseVoiceID })
                let profile = ConversionProfile(id: reference.id, ttsEmbeddingSHA256: base.sha256, converterRevision: revision, referenceAudioSHA256: hash, embedding: embedding)
                try JSONEncoder().encode(profile).write(to: folder.appendingPathComponent("Profiles").appendingPathComponent(reference.id).appendingPathExtension("json"))
                targets[reference.id] = embedding
                records[reference.id] = ["id": reference.id, "baseVoiceID": base.id, "referenceSHA256": hash, "sourcePath": reference.sourcePath, "targetEmbedding": embedding, "status": "embedding-only"]
            } catch {
                records[reference.id] = ["id": reference.id, "status": "rejected-reference", "reason": String(describing: error)]
            }
        }
        XCTAssertFalse(targets.isEmpty, "No reference could be enrolled")
        var convertedFiles: [(String, URL, [Float], Double, Double)] = []
        for reference in bank.profiles.sorted(by: { $0.ttsBaseVoiceID < $1.ttsBaseVoiceID }) {
            guard let target = targets[reference.id], let source = sources[reference.ttsBaseVoiceID] else { continue }
            let url = folder.appendingPathComponent(reference.id).appendingPathExtension("wav")
            do {
                let started = Date()
                let result = try await converter.convert(source: source, target: target, destination: url)
                XCTAssertEqual(result.sourceSeconds, result.outputSeconds, accuracy: 0.04)
                let hash = SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
                records[reference.id]?["audioSHA256"] = hash
                records[reference.id]?["audioSeconds"] = result.outputSeconds
                records[reference.id]?["elapsedSeconds"] = Date().timeIntervalSince(started)
                records[reference.id]?["referenceText"] = text
                records[reference.id]?["sourceEmbedding"] = result.sourceEmbedding
                convertedFiles.append((reference.id, url, target, result.sourceSeconds, result.outputSeconds))
                print("VoiceMatrix bank rendered id=\(reference.id) seconds=\(result.outputSeconds)")
            } catch {
                records[reference.id]?["status"] = "rejected-conversion"
                records[reference.id]?["reason"] = String(describing: error)
            }
        }
        // Batch the independent output embedding pass to avoid reloading converter weights per target.
        for (id, url, target, _, _) in convertedFiles {
            let output = try await converter.extractEmbedding(from: url)
            let source = try XCTUnwrap(records[id]?["sourceEmbedding"] as? [Float])
            let before = OfflineVoiceConverter.cosine(source, target)
            let after = OfflineVoiceConverter.cosine(output, target)
            records[id]?["outputEmbedding"] = output
            records[id]?["targetCosineBefore"] = before
            records[id]?["targetCosineAfter"] = after
            records[id]?["status"] = after > before + 0.02 ? "native-audio-checked-awaiting-ASR" : "rejected-insufficient-target-movement"
        }
        await converter.unload()
        let report: [String: Any] = ["converterRevision": revision, "platform": "iOS Simulator CPU", "referenceText": text, "physicalDeviceVerified": 0, "listeningVerified": 0, "profiles": bank.profiles.compactMap { records[$0.id] }]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: folder.appendingPathComponent("bank-results.json"))
        XCTAssertFalse(convertedFiles.isEmpty, "No real converted audio was generated")
    }
}
