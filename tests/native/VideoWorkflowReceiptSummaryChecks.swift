import Foundation

@main struct VideoWorkflowReceiptSummaryChecks {
    static func event(_ sequence: Int, _ stage: String, time: Double? = nil) -> [String: Any] {
        ["sequence": sequence, "time": time ?? (100 + Double(sequence)), "stage": stage,
         "attempt": 1, "completed": 0, "total": 0, "message": "PRIVATE untrusted backend text"]
    }
    static func video(_ status: String = "awaiting-preparation", active: Bool = false,
                      events: [[String: Any]] = [], history: Bool = true) throws -> VideoWorkflowVideo {
        let data = try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "observedAt": 200.0,
            "videos": [["id": "abcdefghijk", "status": status, "progress": 0.7, "updated": 199.0,
                        "attempts": 1, "nextAttempt": 0.0, "workerLeaseUntil": active ? 250.0 : 0.0,
                        "workerActive": active, "historyAvailable": history, "events": events]]])
        return try VideoWorkflowSnapshot.decode(data).videos[0]
    }
    static func main() throws {
        let received = try video(events: [event(2, "awaiting_preparation"), event(1, "received")])
        precondition(received.receiptEvent?.time == 101)
        precondition(received.processingSummary == "Not processing")
        precondition(received.status.title == "Waiting for voice preparation")
        precondition(VideoWorkflowStage.awaitingPreparation.message == "Waiting before voice preparation.")
        precondition(received.nextAction.contains("voice preparation is waiting"))
        precondition(!received.nextAction.contains("needs reviewed speech segments"))
        precondition(!received.nextAction.contains("permission granted"))
        let missingRuntime = try video(events: [event(1, "candidate_runtime_missing")])
        precondition(missingRuntime.nextAction.contains("speaker-analysis setup"))
        let setupChanged = try video(events: [event(1, "candidate_runtime_missing"), event(2, "candidate_requested")])
        precondition(!setupChanged.nextAction.contains("speaker-analysis setup"))
        let duplicate = try video(events: [event(1, "received"), event(3, "already_queued", time: 99)])
        precondition(duplicate.receiptEvent?.sequence == 3) // Sequence, not clock order.
        precondition(duplicate.receiptEvent?.stage == .alreadyQueued)
        let candidate = try video(events: [event(2, "candidate_requested")])
        precondition(candidate.receiptEvent?.stage == .candidateRequested)
        for stage in ["legacy_snapshot", "synthesizing", "claimed", "review_saved", "unknown"] {
            let item = try video(events: [event(1, stage)], history: false)
            precondition(item.receiptEvent == nil) // Never infer a receipt timestamp.
        }
        for status in ["waiting", "retry", "paused", "awaiting-preparation", "failed", "needs-review"] {
            let item = try video(status, events: [event(1, "synthesizing")])
            precondition(item.processingSummary == "Not processing")
            precondition(!item.nextAction.isEmpty)
            precondition(!item.nextAction.contains("PRIVATE"))
        }
        let running = try video("processing", active: true)
        precondition(running.processingSummary == "Processing reported by laptop")
        let expired = try video("processing", active: false)
        precondition(expired.processingSummary == "Processing not confirmed")
        precondition(expired.nextAction.contains("worker"))
        let unknown = try video("future-status")
        precondition(unknown.processingSummary == "Processing state unknown")
        precondition(VideoWorkflowConnectionDisplay.host("https://laptop.example.ts.net/") == "laptop.example.ts.net")
        precondition(VideoWorkflowConnectionDisplay.host("https://laptop.example.ts.net:8443") == "laptop.example.ts.net:8443")
        for value in [nil, "http://host", "https://user:secret@host", "https://host/private", "https://host?token=secret", "https://host#secret"] as [String?] {
            precondition(VideoWorkflowConnectionDisplay.host(value) == nil)
        }
        for code in [URLError.Code.notConnectedToInternet, .cannotFindHost, .cannotConnectToHost, .networkConnectionLost, .timedOut] {
            precondition(VideoWorkflowConnectionIssue(error: URLError(code)) == .unreachable)
        }
        precondition(VideoWorkflowConnectionIssue(error: VideoWorkflowError.invalidConnection) == .configuration)
        precondition(VideoWorkflowConnectionIssue(error: VideoWorkflowError.invalidSnapshot) == .unverified)
        precondition(VideoWorkflowConnectionIssue(error: NSError(domain: "VoiceMatrix.Connection", code: 1)) == .unverified)
        precondition(VideoWorkflowConnectionIssue(error: URLError(.serverCertificateUntrusted)) == .unverified)
        precondition(VideoWorkflowFreshness.refreshNanoseconds == 30_000_000_000)
        print("Receipt summary checks passed")
    }
}
