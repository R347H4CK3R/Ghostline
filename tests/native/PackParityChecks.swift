import Foundation

@main struct PackParityChecks {
    static func main() async throws {
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let expected = try JSONDecoder().decode([String: Bool].self, from: Data(contentsOf: input.appendingPathComponent("expected.json")))
        let work = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: work) }
        for (name, valid) in expected.sorted(by: { $0.key < $1.key }) {
            let store = CharacterFolderStore(root: work.appendingPathComponent(name))
            var accepted = false
            do {
                let rows = try await store.importCollection(at: input.appendingPathComponent(name))
                precondition(rows.count == 1 && rows[0].id == "neutral")
                accepted = true
            } catch { print("Rejected \(name): \(error.localizedDescription)") }
            precondition(accepted == valid, "Python/native import mismatch: \(name)")
            if !valid { let rows = try await store.profiles(); precondition(rows.isEmpty) }
        }
        print("Native parity passed for \(expected.count) synthetic layouts; no physical-device inference tested")
    }
}
