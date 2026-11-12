import Foundation

struct RVCOnlineImportedAudio: Sendable {
    let name: String
    let data: Data
    let sampleRate: Int
    let seconds: Double
}

enum RVCOnlineFiles {
    /// Read only the explicitly selected file. A capped FileHandle read prevents
    /// a changed file-size attribute from causing an unbounded allocation.
    static func read(_ url: URL) throws -> RVCOnlineImportedAudio {
        guard url.isFileURL else { throw RVCOnlineError.invalidAudio }
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, (44...RVCOnlineWAV.byteLimit).contains(size) else { throw RVCOnlineError.invalidAudio }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        guard let data = try file.read(upToCount: RVCOnlineWAV.byteLimit + 1), data.count == size else { throw RVCOnlineError.invalidAudio }
        let info = try RVCOnlineWAV.inspect(data)
        let name = String(url.lastPathComponent.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }.map(String.init).joined().prefix(120))
        return RVCOnlineImportedAudio(name: name, data: data, sampleRate: info.sampleRate, seconds: info.seconds)
    }
    /// The network already validated the HTTP digest. Recheck the immutable bytes
    /// before making a local playback file; never save a partially received result.
    static func verifiedTemporary(_ data: Data, result: RVCOnlineSnapshot.Result) throws -> URL {
        try RVCOnlineConnection.validateResult(data, headerSHA256: result.sha256, expected: result)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("Converted-RVC-" + UUID().uuidString + ".wav")
        do { try data.write(to: url, options: .atomic); return url }
        catch { TemporaryAudio.discard(url); throw error }
    }
}
