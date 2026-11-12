import Foundation

/// User-authored source-use affirmation; it does not certify rights or identity.
struct VideoCandidateRequest: Codable, Sendable {
    struct SourceUse: Codable, Sendable { let decision: String; let record: String }
    let schemaVersion: Int
    let requestID: String
    let videoURL: String
    let displayName: String
    let sourceUse: SourceUse
    var videoID: String { URLComponents(string: videoURL)?.queryItems?.first(where: { $0.name == "v" })?.value ?? "" }

    init(url: String, displayName: String, approved: Bool, record: String, id: UUID = UUID()) throws {
        guard approved, let parts = URLComponents(string: url.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "https", parts.user == nil, parts.password == nil, parts.port == nil else { throw VideoWorkflowError.invalidSnapshot }
        let path = parts.path.split(separator: "/").map(String.init)
        let identifier: String?
        switch parts.host?.lowercased() {
        case "youtu.be": identifier = path.count == 1 ? path.first : nil
        case "youtube.com", "www.youtube.com", "m.youtube.com":
            if parts.path == "/watch" { identifier = parts.queryItems?.first(where: { $0.name == "v" })?.value }
            else if path.count == 2 && ["live", "shorts", "embed"].contains(path[0]) { identifier = path[1] }
            else { identifier = nil }
        default: identifier = nil
        }
        let cleanName = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanRecord = record.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let identifier, VideoWorkflowSnapshot.validID(identifier), cleanName.count <= 200,
              !cleanName.unicodeScalars.contains(where: { $0.value < 32 }),
              (1...3000).contains(cleanRecord.count) else { throw VideoWorkflowError.invalidSnapshot }
        schemaVersion = 1; requestID = id.uuidString.lowercased()
        videoURL = "https://www.youtube.com/watch?v=" + identifier
        self.displayName = cleanName
        sourceUse = SourceUse(decision: "approved-private-candidates", record: cleanRecord)
    }
    func validateReceipt(_ data: Data) throws {
        struct Receipt: Decodable {
            let schemaVersion: Int; let accepted: Bool; let videoID: String; let requestID: String
            let alreadyRequested: Bool; let format: String; let identityVerified: Bool
        }
        guard data.count <= 16_384 else { throw VideoWorkflowError.invalidSnapshot }
        let receipt = try JSONDecoder().decode(Receipt.self, from: data)
        guard receipt.schemaVersion == 1, receipt.accepted, receipt.requestID == requestID,
              receipt.videoID == videoID, receipt.format == "f5-reference", !receipt.identityVerified else { throw VideoWorkflowError.invalidSnapshot }
    }
}
