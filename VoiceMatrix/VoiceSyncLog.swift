import Foundation

enum VoiceSyncProgress: Sendable, Equatable {
    case requesting, laptopResponded, laptopReceived, laptopValidating
    case laptopValidated(Int, Int), laptopCatalogReady(Int), laptopCatalogSent, laptopFileSent(Int)
    case catalogValidated(Int, Int), downloading(Int, Int), receiving(Int, Int), fileValidated(Int, Int)
    case unchanged, importing, completed(Int), deferred, stopping, stopped, failed, laptopFailed, activityUnavailable
    var source: String {
        switch self {
        case .laptopResponded, .laptopReceived, .laptopValidating, .laptopValidated, .laptopCatalogReady, .laptopCatalogSent, .laptopFileSent, .laptopFailed: return "Laptop"
        default: return "iPhone"
        }
    }
    var message: String {
        switch self {
        case .requesting: return "Sending catalog request. Waiting for laptop receipt…"
        case .laptopResponded: return "Laptop returned the catalog response."
        case .laptopReceived: return "Laptop received this sync request."
        case .laptopValidating: return "Laptop is checking the private collection."
        case let .laptopValidated(done, total): return "Laptop checked \(done) of \(total) voice references."
        case let .laptopCatalogReady(files): return "Laptop prepared \(files) files for transfer."
        case .laptopCatalogSent: return "Laptop sent the catalog."
        case let .laptopFileSent(count): return "Laptop sent \(count) file responses. Phone validation is separate."
        case let .catalogValidated(files, bytes): return "Catalog verified: \(files) files, \(bytes.formatted()) bytes."
        case let .downloading(index, total): return "Requesting file \(index) of \(total)…"
        case let .receiving(bytes, total): return "Receiving current file: \(bytes.formatted()) of \(total.formatted()) bytes."
        case let .fileValidated(index, total): return "Downloaded and verified file \(index) of \(total)."
        case .unchanged: return "Up to date. The saved collection revision matches the laptop."
        case .importing: return "Validating and saving the collection on this iPhone…"
        case let .completed(count): return "Sync complete. \(count) voice references saved for offline use."
        case .deferred: return "Download finished. Import deferred because audio work started. Sync again when finished."
        case .stopping: return "Stop requested. Waiting for the current operation to finish safely…"
        case .stopped: return "Sync stopped. Previously saved voices were kept."
        case .failed: return "Sync failed at the last reported step. Previously saved voices were kept. Check the connection and retry."
        case .laptopFailed: return "Laptop could not finish serving the snapshot. Check the companion and retry."
        case .activityUnavailable: return "Live laptop activity is unavailable. Transfer will continue; receipt is confirmed only when a response arrives."
        }
    }
}

struct VoiceSyncLogEntry: Identifiable, Sendable {
    let id = UUID()
    let date = Date()
    let progress: VoiceSyncProgress
}

struct VoiceSyncRemoteSnapshot: Decodable {
    struct Event: Decodable {
        let sequence: Int
        let stage: String
        let completed, total: Int
        var progress: VoiceSyncProgress? {
            guard (0...2001).contains(completed), (0...2001).contains(total) else { return nil }
            switch stage {
            case "received": return .laptopReceived
            case "validating": return .laptopValidating
            case "validated" where completed <= total: return .laptopValidated(completed, total)
            case "catalog_ready": return .laptopCatalogReady(total)
            case "catalog_sent": return .laptopCatalogSent
            case "file_sent": return .laptopFileSent(completed)
            case "failed", "disconnected": return .laptopFailed
            default: return nil
            }
        }
    }
    let schemaVersion: Int
    let syncID: String
    let events: [Event]
    func newer(than sequence: Int, for identifier: String) -> [Event] {
        guard schemaVersion == 1, syncID == identifier, events.count <= 160 else { return [] }
        return events.filter { $0.sequence > sequence && $0.sequence < 100_000 && $0.progress != nil }.sorted { $0.sequence < $1.sequence }
    }
}
