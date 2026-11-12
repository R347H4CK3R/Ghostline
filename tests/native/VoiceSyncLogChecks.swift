import Foundation

@main struct VoiceSyncLogChecks {
    static func main() throws {
        let id = UUID().uuidString.lowercased()
        let data = try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "syncID": id, "events": [
            ["sequence": 1, "stage": "received", "completed": 0, "total": 0],
            ["sequence": 2, "stage": "validated", "completed": 2, "total": 3],
            ["sequence": 3, "stage": "private transcript text", "completed": 0, "total": 0],
            ["sequence": 4, "stage": "validated", "completed": 10, "total": 3]
        ]])
        let snapshot = try JSONDecoder().decode(VoiceSyncRemoteSnapshot.self, from: data)
        precondition(snapshot.newer(than: 0, for: "another-request").isEmpty)
        let events = snapshot.newer(than: 0, for: id)
        precondition(events.map(\.progress) == [.laptopReceived, .laptopValidated(2, 3)])
        precondition(snapshot.newer(than: 1, for: id).map(\.sequence) == [2])
        precondition(!events.map { $0.progress!.message }.joined().contains("private transcript"))
        precondition(VoiceSyncProgress.requesting.source == "iPhone")
        precondition(VoiceSyncProgress.laptopReceived.source == "Laptop")
        precondition(VoiceSyncProgress.fileValidated(1, 3).message.contains("verified"))
        precondition(VoiceSyncProgress.completed(60).message.contains("saved"))
        print("Sync log request correlation, deduplication, stage allowlist and source labels passed")
    }
}
