import Foundation

@main struct CharacterReviewChecks {
    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = CharacterReviewStore(root: root)
        let reference = String(repeating: "a", count: 64), generated = String(repeating: "b", count: 64), replacement = String(repeating: "c", count: 64)
        try await store.record(id: "original-test", referenceHash: reference, generatedHash: generated, decision: .matches, categories: ["Animation", "Fantasy"])
        let reloaded = CharacterReviewStore(root: root)
        let accepted = try await reloaded.latest(id: "original-test", referenceHash: reference)
        precondition(accepted?.decision == .matches && accepted?.generatedSHA256 == generated)
        precondition(accepted?.categories == ["Animation", "Fantasy"])
        let changed = try await reloaded.latest(id: "original-test", referenceHash: replacement)
        precondition(changed == nil, "A changed reference must never inherit approval")
        try await store.record(id: "original-test", referenceHash: reference, generatedHash: generated, decision: .different, categories: ["Animation"])
        let rejected = try await store.latest(id: "original-test", referenceHash: reference)
        precondition(rejected?.decision == .different)
        try await store.record(id: "original-test", referenceHash: replacement, generatedHash: generated, decision: .unsure, categories: ["Animation"])
        let unsure = try await store.latest(id: "original-test", referenceHash: replacement)
        precondition(unsure?.decision == .unsure)
        let history = try await store.history(id: "original-test")
        precondition(history.count == 3, "Review history must survive changes")
        do {
            try await store.record(id: "original-test", referenceHash: "invalid", generatedHash: generated, decision: .matches, categories: ["Animation"])
            fatalError("Invalid hash was accepted")
        } catch is CharacterReviewError { }
        let unchanged = try await store.history(id: "original-test")
        precondition(unchanged.count == 3, "Failed writes must preserve history")
        print("Native listening review persistence and reference invalidation passed")
    }
}
