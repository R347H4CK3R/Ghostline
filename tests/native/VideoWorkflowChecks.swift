import Foundation

@main struct VideoWorkflowChecks {
    static let identifier = "EAT0nWoEzJ8"
    static func event(_ sequence: Int, stage: String = "received") -> [String: Any] {
        ["sequence": sequence, "time": 1_700_000_000.0 + Double(sequence), "stage": stage,
         "message": "PRIVATE TRANSCRIPT /private/path", "attempt": 1, "completed": 0, "total": 0]
    }
    static func video(status: String = "needs-review", history: Bool = true,
                      events: [[String: Any]] = [event(1)]) -> [String: Any] {
        ["id": identifier, "status": status, "progress": 1.0, "updated": 1_700_000_005.0,
         "attempts": 1, "nextAttempt": 0.0, "workerLeaseUntil": 0.0, "workerActive": false,
         "historyAvailable": history, "events": events]
    }
    static func decode(_ videos: [[String: Any]], schema: Int = 1, for id: String? = nil) throws -> VideoWorkflowSnapshot {
        let data = try JSONSerialization.data(withJSONObject: ["schemaVersion": schema, "observedAt": 1_700_000_010.0, "videos": videos])
        return try VideoWorkflowSnapshot.decode(data, videoID: id)
    }
    static func rejects(_ operation: () throws -> Void) {
        do { try operation(); preconditionFailure("Expected rejection") } catch { }
    }
    static func main() async throws {
        for path in CommandLine.arguments.dropFirst() {
            let backend = try VideoWorkflowSnapshot.decode(Data(contentsOf: URL(fileURLWithPath: path)))
            precondition(backend.videos.count == 1)
            precondition(backend.videos[0].id == identifier)
            precondition(backend.videos[0].status == .waiting)
            precondition(backend.videos[0].events.first?.stage == .received)
        }
        let snapshot = try decode([video(events: [event(4, stage: "synthesizing"), event(2, stage: "received")])])
        let first = snapshot.videos[0]
        precondition(first.status == .needsReview)
        precondition(first.status.title == "Technical processing ended; review pending")
        precondition(first.events.map(\.sequence) == [2, 4])
        precondition(!first.events.map(\.message).joined().contains("PRIVATE"))
        // Historical synthesis cannot replace a newer pause in the current snapshot.
        let paused = try decode([video(status: "awaiting-preparation", events: [event(9, stage: "synthesizing")])]).videos[0]
        precondition(paused.status == .awaitingPreparation)
        precondition(paused.status.title == "Waiting for voice preparation")
        let duplicate = try decode([video(events: [event(3, stage: "already_queued")])]).videos[0]
        precondition(duplicate.events[0].stage == .alreadyQueued)
        precondition(duplicate.events[0].message.contains("existing queue entry"))
        let expired = try decode([video(events: [event(3, stage: "lease_expired")])]).videos[0]
        precondition(expired.events[0].message.contains("lease expired"))
        let uninstrumented = try decode([video(status: "processing")]).videos[0]
        precondition(uninstrumented.workerHistoryNotice?.contains("may predate verbose logging") == true)
        let reviewWithoutStages = try decode([video()]).videos[0]
        precondition(reviewWithoutStages.workerHistoryNotice != nil)
        var previousAttempt = event(2, stage: "synthesizing"); previousAttempt["attempt"] = 0
        let missingCurrentAttempt = try decode([video(status: "processing", events: [previousAttempt])]).videos[0]
        precondition(missingCurrentAttempt.workerHistoryNotice != nil)
        let instrumented = try decode([video(status: "processing", events: [event(2, stage: "claimed")])]).videos[0]
        precondition(instrumented.workerHistoryNotice == nil)
        precondition(paused.workerHistoryNotice == nil)
        let unknown = try decode([video(status: "private status", events: [event(1, stage: "private transcript")])]).videos[0]
        precondition(unknown.status == .unknown)
        precondition(unknown.events[0].message == "Unrecognized laptop event. Update the app to read this stage.")
        let legacy = try decode([video(history: false, events: [event(1, stage: "legacy_snapshot")])]).videos[0]
        precondition(legacy.historyNotice.contains("unavailable"))
        precondition(first.historyNotice.contains("limited"))
        let empty = try decode([], for: identifier)
        precondition(empty.videos.isEmpty)
        rejects { _ = try decode([video()], schema: 2) }
        rejects { _ = try decode([video()], for: "different01") }
        rejects { _ = try decode(Array(repeating: video(), count: 201)) }
        rejects { _ = try decode([video(), video()]) }
        rejects { _ = try decode([video(events: (1...161).map { event($0) })]) }
        rejects { _ = try decode([video(events: [event(1), event(1)])]) }
        var bad = video(); bad["progress"] = 1.1
        rejects { _ = try decode([bad]) }
        bad = video(); bad["id"] = "bad/id"
        rejects { _ = try decode([bad]) }
        bad = video(); bad["updated"] = -1
        rejects { _ = try decode([bad]) }
        var badEvent = event(1); badEvent["completed"] = -1
        rejects { _ = try decode([video(events: [badEvent])]) }
        rejects { _ = try VideoWorkflowSnapshot.decode(Data(repeating: 32, count: VideoWorkflowSnapshot.byteLimit + 1)) }
        let root = URL(string: "https://laptop.example/")!
        let endpoint = try VideoWorkflowSnapshot.endpoint(root: root, videoID: identifier)
        precondition(endpoint.absoluteString == "https://laptop.example/workflow?video=EAT0nWoEzJ8")
        let allEndpoint = try VideoWorkflowSnapshot.endpoint(root: root)
        precondition(allEndpoint.path == "/workflow")
        for invalid in ["http://laptop.example", "https://user@laptop.example", "https://laptop.example/path", "https://laptop.example/?token=secret", "https://laptop.example/#fragment"] {
            rejects { _ = try VideoWorkflowSnapshot.endpoint(root: URL(string: invalid)!) }
        }
        rejects { _ = try VideoWorkflowSnapshot.endpoint(root: root, videoID: "abc") }
        var submissions = VideoWorkflowSubmissionLog()
        for _ in 0..<100 {
            let attempt = submissions.begin(count: 2)
            submissions.finish(attempt: attempt, outcome: .accepted)
        }
        precondition(submissions.events.count == 80)
        precondition(submissions.events.last?.attempt == 100)
        precondition(submissions.events.last?.stage == .accepted)
        precondition(submissions.events.last!.message.contains("not confirm"))
        let attempt = submissions.begin(count: 1)
        submissions.finish(attempt: attempt, outcome: .failed)
        precondition(submissions.events.last!.message.contains("unconfirmed"))
        let request = try JSONSerialization.data(withJSONObject: ["videos": [["id": identifier, "url": "https://www.youtube.com/watch?v=" + identifier, "name": "Private name"]]])
        let receipt: [String: Any] = ["added": [identifier], "duplicates": [], "namesStored": true, "pipelineConnected": false]
        try VideoWorkflowReceipt.validate(try JSONSerialization.data(withJSONObject: receipt), submitted: request)
        var duplicateReceipt = receipt; duplicateReceipt["added"] = []; duplicateReceipt["duplicates"] = [identifier]
        try VideoWorkflowReceipt.validate(try JSONSerialization.data(withJSONObject: duplicateReceipt), submitted: request)
        for body in [Data("<html>Login</html>".utf8), Data("{}".utf8)] {
            rejects { try VideoWorkflowReceipt.validate(body, submitted: request) }
        }
        for modified in [["added": [], "duplicates": [], "namesStored": true],
                         ["added": [identifier], "duplicates": [identifier], "namesStored": true],
                         ["added": ["SYNTHETIC03"], "duplicates": [], "namesStored": true],
                         ["added": [identifier], "duplicates": [], "namesStored": false]] as [[String: Any]] {
            rejects { try VideoWorkflowReceipt.validate(JSONSerialization.data(withJSONObject: modified), submitted: request) }
        }
        let wrongRequest = try JSONSerialization.data(withJSONObject: ["videos": [["id": identifier, "url": "https://www.youtube.com/watch?v=SYNTHETIC03"]]])
        rejects { try VideoWorkflowReceipt.validate(JSONSerialization.data(withJSONObject: receipt), submitted: wrongRequest) }
        precondition(VideoWorkflowFreshness.refreshNanoseconds == 30_000_000_000)
        precondition(!VideoWorkflowFreshness.isStale(lastFetched: 100, now: 131))
        precondition(VideoWorkflowFreshness.isStale(lastFetched: 100, now: 176))
        precondition(VideoWorkflowFreshness.isStale(lastFetched: nil, now: 100))
        var staged = video(status: "processing", events: [event(2, stage: "synthesizing"), event(3, stage: "already_queued")])
        staged["currentStage"] = "synthesizing"; staged["currentStageAt"] = 1_700_000_002.0
        staged["lastEventAt"] = 1_700_000_003.0
        let current = try decode([staged]).videos[0]
        precondition(current.lastRecordedStage == .synthesizing)
        precondition(current.lastRecordedStageAt == 1_700_000_002.0)
        let catalog: [String: Any] = ["schemaVersion": 1, "state": "current", "count": 1,
            "checkedAt": 100.0, "lastChangedAt": 100.0,
            "voices": [["id": String(repeating: "a", count: 64), "name": "Voice One", "firstObservedAt": 100.0, "lastChangedAt": 100.0]],
            "events": [["sequence": 1, "time": 100.0, "kind": "observed", "voiceID": String(repeating: "a", count: 64), "name": "Voice One"]]]
        let catalogData = try JSONSerialization.data(withJSONObject: catalog)
        let voiceList = try JSONDecoder().decode(WorkflowVoiceCatalog.self, from: catalogData)
        precondition(voiceList.isValid && voiceList.voices[0].displayName == "Voice One")
        precondition(voiceList.events[0].message.contains("First observed"))
        for privateName in ["/Users/private", "token=private", "Bearer private", "https://private", "line\nprivate"] {
            precondition(WorkflowVoiceCatalog.safeName(privateName) == "Name hidden")
        }
        var invalidCatalog = catalog; invalidCatalog["count"] = 2
        let invalidList = try JSONDecoder().decode(WorkflowVoiceCatalog.self, from: JSONSerialization.data(withJSONObject: invalidCatalog))
        precondition(!invalidList.isValid)
        let probe = FetchProbe(snapshot: snapshot)
        let gate = VideoWorkflowRequestGate()
        let firstFetch = Task { try await gate.fetch { await probe.wait() } }
        while await probe.count == 0 { await Task.yield() }
        let overlapping = try await gate.fetch { await probe.wait() }
        precondition(overlapping == nil)
        firstFetch.cancel()
        await probe.complete()
        do { _ = try await firstFetch.value; preconditionFailure("Canceled result must be discarded") }
        catch is CancellationError { }
        let next = try await gate.fetch { snapshot }
        precondition(next?.videos.count == 1)
        let calls = await probe.count
        precondition(calls == 1)
        print("Workflow checks passed: bounds, privacy, current state, gaps, endpoint security, submissions, cancellation and no overlap")
    }
}

private actor FetchProbe {
    let snapshot: VideoWorkflowSnapshot
    var count = 0
    var continuation: CheckedContinuation<VideoWorkflowSnapshot, Never>?
    init(snapshot: VideoWorkflowSnapshot) { self.snapshot = snapshot }
    func wait() async -> VideoWorkflowSnapshot {
        count += 1
        return await withCheckedContinuation { continuation = $0 }
    }
    func complete() { continuation?.resume(returning: snapshot); continuation = nil }
}
