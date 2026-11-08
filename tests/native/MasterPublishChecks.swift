import Foundation

@main struct MasterPublishChecks {
    static func main() async throws {
        let fm = FileManager.default
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let work = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: work) }
        let store = CharacterFolderStore(root: work)
        let first = try await store.importCollection(at: input.appendingPathComponent("Initial"))
        precondition(first.count == 1 && first[0].id == "original-test")
        let oldURL = try await store.referenceURL(id: "original-test")
        let oldBytes = try Data(contentsOf: oldURL)
        let expanded = try await store.importCollection(at: input.appendingPathComponent("Voices"))
        precondition(Set(expanded.map(\.id)) == Set(["original-test", "second-test"]))
        precondition(expanded.allSatisfy { $0.categories == ["Animation", "Fantasy"] })
        let currentURL = try await store.referenceURL(id: "original-test")
        let currentBytes = try Data(contentsOf: currentURL)
        precondition(currentBytes == oldBytes)
        // Ignore external folder loss; imported reference copies remain local.
        try fm.removeItem(at: input.appendingPathComponent("Voices"))
        let cachedURL = try await store.referenceURL(id: "second-test")
        let cachedBytes = try Data(contentsOf: cachedURL)
        precondition(cachedBytes.count > 24000)
        print("Native import passed: published additions, preserved original, unchanged categories and private offline copies")
    }
}
