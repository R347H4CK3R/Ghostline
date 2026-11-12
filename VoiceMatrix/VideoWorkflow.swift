import Foundation

/// A read-only snapshot. Historical events never determine the current job state.
struct VideoWorkflowSnapshot: Decodable, Sendable {
    static let byteLimit = 2 * 1_024 * 1_024
    let schemaVersion: Int
    let observedAt: TimeInterval
    let hasMore: Bool?
    let eventLimit: Int?
    let videos: [VideoWorkflowVideo]
    let catalog: WorkflowVoiceCatalog?

    static func decode(_ data: Data, videoID: String? = nil) throws -> Self {
        guard data.count <= byteLimit else { throw VideoWorkflowError.invalidSnapshot }
        let result = try JSONDecoder().decode(Self.self, from: data)
        guard result.schemaVersion == 1, validTime(result.observedAt), result.videos.count <= 200,
              Set(result.videos.map(\.id)).count == result.videos.count,
              result.videos.allSatisfy(\.isValid), result.catalog?.isValid ?? true,
              result.eventLimit.map({ (1...160).contains($0) }) ?? true else { throw VideoWorkflowError.invalidSnapshot }
        if let videoID {
            guard validID(videoID), result.videos.count <= 1,
                  result.videos.allSatisfy({ $0.id == videoID }) else { throw VideoWorkflowError.invalidSnapshot }
        }
        return result
    }

    static func validID(_ value: String) -> Bool {
        value.utf8.count == 11 && value.range(of: "^[A-Za-z0-9_-]{11}$", options: .regularExpression) != nil
    }
    static func validTime(_ value: TimeInterval) -> Bool { value.isFinite && (0...253_402_300_799).contains(value) }
    static func endpoint(root: URL, videoID: String? = nil) throws -> URL {
        guard root.scheme == "https", root.host?.isEmpty == false,
              root.user == nil, root.password == nil, root.query == nil, root.fragment == nil,
              root.path.isEmpty || root.path == "/" else { throw VideoWorkflowError.invalidConnection }
        var parts = URLComponents(url: root.appendingPathComponent("workflow"), resolvingAgainstBaseURL: false)
        if let videoID {
            guard validID(videoID) else { throw VideoWorkflowError.invalidSnapshot }
            parts?.queryItems = [URLQueryItem(name: "video", value: videoID)]
        }
        guard let url = parts?.url else { throw VideoWorkflowError.invalidConnection }
        return url
    }
}

enum VideoWorkflowError: LocalizedError {
    case invalidSnapshot, invalidConnection
    var errorDescription: String? {
        switch self {
        case .invalidSnapshot: return "The laptop workflow response could not be verified."
        case .invalidConnection: return "Connect your laptop using its HTTPS pairing file first."
        }
    }
}

enum VideoWorkflowStatus: String, Decodable, Sendable {
    case waiting, retry, paused, processing, failed, unknown
    case awaitingPreparation = "awaiting-preparation"
    case needsReview = "needs-review"
    init(from decoder: Decoder) throws {
        self = Self(rawValue: try decoder.singleValueContainer().decode(String.self)) ?? .unknown
    }
    var title: String {
        switch self {
        case .waiting: return "Waiting for a laptop worker"
        case .retry: return "Waiting to retry"
        case .paused: return "Paused on the laptop"
        case .awaitingPreparation: return "Waiting for reviewed speech segments"
        case .processing: return "Processing on the laptop"
        case .needsReview: return "Technical processing ended; review pending"
        case .failed: return "Failed on the laptop"
        case .unknown: return "Unrecognized laptop status"
        }
    }
}

struct VideoWorkflowVideo: Decodable, Identifiable, Sendable {
    let id: String
    let status: VideoWorkflowStatus
    let progress: Double
    let updated: TimeInterval
    let attempts: Int
    let nextAttempt: TimeInterval
    let workerLeaseUntil: TimeInterval
    let workerActive: Bool
    let historyAvailable: Bool
    let currentStage: VideoWorkflowStage?
    let currentStageAt: TimeInterval?
    let lastEventAt: TimeInterval?
    private let recordedEvents: [VideoWorkflowEvent]
    enum CodingKeys: String, CodingKey {
        case id, status, progress, updated, attempts, nextAttempt, workerLeaseUntil, workerActive, historyAvailable
        case currentStage, currentStageAt, lastEventAt
        case recordedEvents = "events"
    }
    var events: [VideoWorkflowEvent] { recordedEvents.sorted { $0.sequence < $1.sequence } }
    var lastRecordedStage: VideoWorkflowStage? {
        currentStage ?? events.last(where: { $0.attempt == attempts && $0.stage.isWorkerStage })?.stage
    }
    var lastRecordedStageAt: TimeInterval? {
        currentStageAt ?? events.last(where: { $0.attempt == attempts && $0.stage.isWorkerStage })?.time
    }
    var isValid: Bool {
        VideoWorkflowSnapshot.validID(id) && progress.isFinite && (0...1).contains(progress)
            && VideoWorkflowSnapshot.validTime(updated) && VideoWorkflowSnapshot.validTime(nextAttempt)
            && VideoWorkflowSnapshot.validTime(workerLeaseUntil) && (0...1_000_000).contains(attempts)
            && [currentStageAt, lastEventAt].allSatisfy { $0.map(VideoWorkflowSnapshot.validTime) ?? true }
            && recordedEvents.count <= 160 && recordedEvents.allSatisfy(\.isValid)
            && Set(recordedEvents.map(\.sequence)).count == recordedEvents.count
    }
    var workerHistoryNotice: String? {
        guard status == .processing || status == .needsReview,
              currentStage?.isWorkerStage != true,
              !recordedEvents.contains(where: { $0.attempt == attempts && $0.stage.isWorkerStage }) else { return nil }
        return "No worker stages are retained for this attempt. The worker may predate verbose logging; no missing stages are inferred."
    }
    var historyNotice: String {
        if !historyAvailable { return "Earlier history is unavailable or partial. Only the current snapshot and retained events can be shown." }
        return "History is limited to retained recorded events. Unreported steps cannot be reconstructed."
    }
}

enum VideoWorkflowStage: String, Decodable, Sendable {
    case received, claimed, resumed, paused, retry, failed, synthesizing, publishing, progress, extracting, transcribing, unknown
    case alreadyQueued = "already_queued"
    case candidateRuntimeMissing = "candidate_runtime_missing"
    case candidateRequested = "candidate_requested", speakerAnalyzing = "speaker_analyzing", temporaryMediaRemoved = "temporary_media_removed"
    case awaitingPreparation = "awaiting_preparation", reviewSaved = "review_saved"
    case inspectionRequested = "inspection_requested", inspectionStopRequested = "inspection_stop_requested"
    case inspectionStarted = "inspection_started", inspectionReady = "inspection_ready", inspectionAnalyzing = "inspection_analyzing"
    case preparationStarted = "preparation_started", preparationReady = "preparation_ready"
    case referencesChecking = "references_checking", modelLoading = "model_loading"
    case audioChecking = "audio_checking", wordsChecking = "words_checking", needsReview = "needs_review"
    case legacySnapshot = "legacy_snapshot", downloadStarted = "download_started", downloadFinished = "download_finished"
    case mediaChecking = "media_checking", listeningRecorded = "listening_recorded", leaseExpired = "lease_expired"
    init(from decoder: Decoder) throws {
        self = Self(rawValue: try decoder.singleValueContainer().decode(String.self)) ?? .unknown
    }
    var isWorkerStage: Bool {
        switch self {
        case .speakerAnalyzing, .temporaryMediaRemoved, .claimed, .resumed, .preparationStarted, .preparationReady, .inspectionStarted,
             .inspectionAnalyzing, .inspectionReady, .downloadStarted, .downloadFinished,
             .mediaChecking, .extracting, .transcribing, .referencesChecking, .modelLoading,
             .synthesizing, .audioChecking, .wordsChecking, .publishing, .needsReview, .progress:
            return true
        default: return false
        }
    }
    var message: String {
        switch self {
        case .candidateRuntimeMissing: return "Automatic candidates are waiting for laptop speaker-analysis setup."
        case .candidateRequested: return "Laptop saved the private voice-candidate request. Character identities are unreviewed."
        case .speakerAnalyzing: return "Laptop is grouping possible speakers. Overlap and character identity remain unverified."
        case .temporaryMediaRemoved: return "Temporary downloaded media was removed. Reference audio and existing voices remain."
        case .received: return "Laptop received this video request."
        case .alreadyQueued: return "Laptop received this link again; the existing queue entry was kept."
        case .claimed: return "A laptop worker claimed the request."
        case .resumed: return "Laptop resumed the request."
        case .awaitingPreparation: return "Waiting for reviewed speech segments before voice preparation."
        case .paused: return "Laptop paused this request."
        case .retry: return "Laptop scheduled another attempt."
        case .leaseExpired: return "The laptop worker lease expired before the stage finished."
        case .failed: return "Laptop reported a failed attempt. Check the companion for details."
        case .reviewSaved: return "Speech segment review was saved on the laptop."
        case .inspectionRequested: return "Source inspection was requested."
        case .inspectionStopRequested: return "Stopping source inspection was requested."
        case .inspectionStarted: return "Source inspection started."
        case .inspectionReady: return "Source inspection is ready for review."
        case .inspectionAnalyzing: return "Laptop is analyzing the source inspection."
        case .preparationStarted: return "Voice reference preparation started."
        case .preparationReady: return "Voice references are prepared for processing."
        case .referencesChecking: return "Laptop is checking voice references."
        case .modelLoading: return "Laptop is loading the voice model."
        case .synthesizing: return "Laptop is creating voice audio."
        case .audioChecking: return "Laptop is checking generated audio."
        case .wordsChecking: return "Laptop is checking spoken words."
        case .publishing: return "Laptop is preparing the private review collection."
        case .needsReview: return "Voice processing reached listening review. This is not completion or phone sync."
        case .progress: return "Laptop reported processing progress."
        case .legacySnapshot: return "Existing request snapshot recorded. Earlier events are unavailable."
        case .downloadStarted: return "Laptop is attempting the source media download."
        case .downloadFinished: return "Source media download finished."
        case .mediaChecking: return "Laptop is checking the source media."
        case .extracting: return "Laptop is extracting source audio."
        case .transcribing: return "Laptop is transcribing source speech."
        case .listeningRecorded: return "A listening review decision was recorded. It does not confirm phone sync."
        case .unknown: return "Unrecognized laptop event. Update the app to read this stage."
        }
    }
}

struct VideoWorkflowEvent: Decodable, Identifiable, Sendable {
    let sequence: Int
    let time: TimeInterval
    let stage: VideoWorkflowStage
    let attempt: Int
    let completed: Int
    let total: Int
    var id: Int { sequence }
    // Ignore backend text entirely. No names, transcripts, paths or failure details enter this log.
    var message: String { stage.message }
    var isValid: Bool {
        sequence > 0 && VideoWorkflowSnapshot.validTime(time) && (0...1_000_000).contains(attempt)
            && (0...1_000_000).contains(completed) && (0...1_000_000).contains(total)
            && (total == 0 || completed <= total)
    }
}

/// Serializes refreshes even when an old view task is still unwinding after cancellation.
actor VideoWorkflowRequestGate {
    private var inFlight = false
    func fetch(_ operation: @Sendable () async throws -> VideoWorkflowSnapshot) async throws -> VideoWorkflowSnapshot? {
        guard !inFlight else { return nil }
        try Task.checkCancellation()
        inFlight = true
        defer { inFlight = false }
        let snapshot = try await operation()
        try Task.checkCancellation()
        return snapshot
    }
}

/// Lives only in VideoQueueView state. No video identifiers or user text are retained.
struct VideoWorkflowSubmissionLog {
    enum Stage { case sending, accepted, failed, interrupted }
    struct Entry: Identifiable {
        let id = UUID()
        let date = Date()
        let attempt: Int
        let count: Int
        let stage: Stage
        var message: String {
            switch stage {
            case .sending: return "iPhone is sending \(count) video requests. Laptop receipt is not yet confirmed."
            case .accepted: return "Laptop accepted the list. This does not confirm processing, review or saving voices on this iPhone."
            case .failed: return "iPhone did not receive an acceptance response. Laptop receipt is unconfirmed; check the workflow before retrying."
            case .interrupted: return "iPhone stopped waiting for acceptance. Laptop receipt is unconfirmed; check the workflow."
            }
        }
    }
    private(set) var events: [Entry] = []
    private var attempt = 0
    mutating func begin(count: Int) -> Int {
        attempt += 1
        record(Entry(attempt: attempt, count: count, stage: .sending))
        return attempt
    }
    mutating func finish(attempt: Int, outcome: Stage) {
        guard outcome != .sending else { return }
        record(Entry(attempt: attempt, count: 0, stage: outcome))
    }
    private mutating func record(_ event: Entry) {
        events.append(event)
        if events.count > 80 { events.removeFirst(events.count - 80) }
    }
}


/// A successful HTTP status alone is not a queue receipt (a proxy can return HTML).
enum VideoWorkflowReceipt {
    private struct Submission: Decodable {
        struct Video: Decodable { let id: String; let url: String }
        let videos: [Video]
    }
    private struct Receipt: Decodable {
        let added: [String]
        let duplicates: [String]
        let namesStored: Bool
    }
    static func validate(_ data: Data, submitted: Data) throws {
        guard data.count <= 65_536, submitted.count <= 65_536 else { throw VideoWorkflowError.invalidSnapshot }
        let request = try JSONDecoder().decode(Submission.self, from: submitted)
        let receipt = try JSONDecoder().decode(Receipt.self, from: data)
        let ids = request.videos.map(\.id)
        let acknowledged = receipt.added + receipt.duplicates
        guard (1...200).contains(ids.count), Set(ids).count == ids.count,
              request.videos.allSatisfy({ VideoWorkflowSnapshot.validID($0.id) && $0.url == "https://www.youtube.com/watch?v=" + $0.id }),
              receipt.namesStored, acknowledged.count == ids.count,
              Set(acknowledged).count == acknowledged.count,
              Set(acknowledged) == Set(ids) else { throw VideoWorkflowError.invalidSnapshot }
    }
}


/// Connection freshness is distinct from worker progress and stage duration.
enum VideoWorkflowFreshness {
    static let refreshNanoseconds: UInt64 = 30_000_000_000
    static func isStale(lastFetched: TimeInterval?, now: TimeInterval) -> Bool {
        guard let lastFetched else { return true }
        return now - lastFetched > 75
    }
}

/// Catalog observation times never claim exact publication times or phone saving.
struct WorkflowVoiceCatalog: Decodable, Sendable {
    enum State: String, Decodable, Sendable {
        case notChecked = "not_checked", checking, current, unavailable
    }
    struct Voice: Decodable, Identifiable, Sendable {
        let id, name: String
        let firstObservedAt, lastChangedAt: TimeInterval
        var displayName: String { WorkflowVoiceCatalog.safeName(name) }
        var isValid: Bool {
            WorkflowVoiceCatalog.validID(id) && name.count <= 120
                && VideoWorkflowSnapshot.validTime(firstObservedAt) && VideoWorkflowSnapshot.validTime(lastChangedAt)
        }
    }
    struct Event: Decodable, Identifiable, Sendable {
        enum Kind: String, Decodable, Sendable { case observed, added, changed, missing }
        let sequence: Int
        let time: TimeInterval
        let kind: Kind
        let voiceID, name: String
        var id: Int { sequence }
        var message: String {
            let label = WorkflowVoiceCatalog.safeName(name)
            switch kind {
            case .observed: return "First observed in laptop list: \(label)"
            case .added: return "New in observed laptop list: \(label)"
            case .changed: return "Changed in laptop list: \(label). Downloaded copies were not replaced."
            case .missing: return "No longer in observed laptop list: \(label). Downloaded copies were not removed."
            }
        }
        var isValid: Bool {
            sequence > 0 && VideoWorkflowSnapshot.validTime(time) && WorkflowVoiceCatalog.validID(voiceID) && name.count <= 120
        }
    }
    let schemaVersion: Int
    let state: State
    let count: Int
    let checkedAt, lastChangedAt: TimeInterval?
    let voices: [Voice]
    let events: [Event]
    var isValid: Bool {
        schemaVersion == 1 && (0...1000).contains(count) && voices.count == count
            && Set(voices.map(\.id)).count == voices.count && voices.allSatisfy(\.isValid)
            && events.count <= 160 && events.allSatisfy(\.isValid)
            && Set(events.map(\.sequence)).count == events.count
            && [checkedAt, lastChangedAt].allSatisfy { $0.map(VideoWorkflowSnapshot.validTime) ?? true }
    }
    static func validID(_ value: String) -> Bool {
        value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
    }
    static func safeName(_ value: String) -> String {
        let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let forbidden = CharacterSet.controlCharacters.union(.illegalCharacters).union(CharacterSet(charactersIn: "/\\:=<>@"))
        guard (1...120).contains(value.count), value.utf8.count <= 160, !clean.isEmpty,
              value.rangeOfCharacter(from: forbidden) == nil,
              value.range(of: "(?i)\\b(bearer|token|password|secret|api[ _-]?key)\\b|[A-Za-z0-9_-]{32,}", options: .regularExpression) == nil else { return "Name hidden" }
        return clean
    }
}
