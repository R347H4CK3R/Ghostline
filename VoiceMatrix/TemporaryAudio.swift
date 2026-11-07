import Foundation

enum TemporaryAudio {
    static let prefixes = ["Speech-", "Recording-", "Imported-"]
    static func discard(_ url: URL?) {
        guard let url,
              url.deletingLastPathComponent().standardizedFileURL == FileManager.default.temporaryDirectory.standardizedFileURL,
              prefixes.contains(where: { url.lastPathComponent.hasPrefix($0) }) else { return }
        try? FileManager.default.removeItem(at: url)
    }
    static func cleanPreviousSession() {
        let root = FileManager.default.temporaryDirectory
        for url in (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] { discard(url) }
    }
}
