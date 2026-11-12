import Foundation
import CryptoKit

actor SyncProgressRecorder {
    private var values: [VoiceSyncProgress] = []
    func append(_ value: VoiceSyncProgress) { values.append(value) }
    func all() -> [VoiceSyncProgress] { values }
}

@main struct VoiceFolderSyncChecks {
    static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func main() async throws {
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let work = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: work) }
        var blobs: [String: Data] = [:]
        for path in ["collection.json", "original-test/manifest.json", "original-test/reference.wav"] { blobs[path] = try Data(contentsOf: input.appendingPathComponent(path)) }
        let files = blobs.sorted { $0.key < $1.key }.map { ["path": $0.key, "sha256": hash($0.value), "bytes": $0.value.count] as [String: Any] }
        func catalog(_ rows: [[String: Any]]) throws -> (Data, String) {
            let proof = rows.sorted { ($0["path"] as! String) < ($1["path"] as! String) }.map { ($0["path"] as! String) + ":" + ($0["sha256"] as! String) + ":" + String($0["bytes"] as! Int) + "\n" }.joined()
            let revision = hash(Data(proof.utf8))
            return (try JSONSerialization.data(withJSONObject: ["schemaVersion":1,"revision":revision,"files":rows]),revision)
        }
        let (index, revision) = try catalog(files)
        var calls = 0
        func fetch(_ path: String, _ limit: Int) async throws -> Data {
            calls += 1
            if path == "voices" { return index }
            precondition(path.hasPrefix("voices/" + revision + "/"))
            return blobs[String(path.dropFirst(("voices/" + revision + "/").count))]!
        }
        let staged = work.appendingPathComponent("staged")
        let events = SyncProgressRecorder()
        let downloaded = try await VoiceFolderSync.download(to: staged, previousRevision: nil, progress: { await events.append($0) }, fetch: fetch)
        let recorded = await events.all()
        precondition(recorded.first == .catalogValidated(3, blobs.values.reduce(0) { $0 + $1.count }))
        precondition(recorded.last == .fileValidated(3, 3))
        precondition(recorded.filter { if case .fileValidated = $0 { return true }; return false }.count == 3)
        precondition(downloaded == revision && calls == 4)
        let store = CharacterFolderStore(root: work.appendingPathComponent("private"))
        let profiles = try await store.importCollection(at: staged)
        precondition(profiles.count == 1 && profiles[0].id == "original-test")
        calls = 0
        let unchanged = try await VoiceFolderSync.download(to: work.appendingPathComponent("unchanged"), previousRevision: revision, fetch: fetch)
        precondition(unchanged == nil && calls == 1)
        var escaped = files; escaped[1]["path"] = "../outside.wav"
        let (badIndex, _) = try catalog(escaped)
        do {
            _ = try await VoiceFolderSync.download(to: work.appendingPathComponent("bad"), previousRevision: nil) { path, limit in badIndex }
            fatalError("Unsafe path accepted")
        } catch { }
        do {
            _ = try await VoiceFolderSync.download(to: work.appendingPathComponent("corrupt"), previousRevision: nil) { path, limit in path == "voices" ? index : Data("changed bytes".utf8) }
            fatalError("Corrupt transferred bytes accepted")
        } catch { }
        let stillSaved = try await store.profiles()
        precondition(stillSaved == profiles)
        let started = ContinuousClock.now
        do {
            _ = try await VoiceFolderSync.bounded(seconds: 0.02, onTimeout: {}) {
                try await Task.sleep(nanoseconds: 1_000_000_000)
                return true
            }
            fatalError("Overall transfer deadline was ignored")
        } catch { }
        precondition(started.duration(to: .now) < .seconds(0.5))
        print("Private transfer staging, native folder import, unchanged catalog and unsafe/corrupt transfer checks passed")
    }
}
