import Foundation
@main struct VideoCandidateRequestChecks {
    static func rejects(_ action: () throws -> Void) { do { try action(); preconditionFailure("Expected rejection") } catch {} }
    static func main() throws {
        let request = try VideoCandidateRequest(url: "https://youtu.be/EAT0nWoEzJ8?t=1", displayName: "Source hint", approved: true, record: "My original recording")
        precondition(request.videoID == "EAT0nWoEzJ8")
        precondition(request.videoURL == "https://www.youtube.com/watch?v=EAT0nWoEzJ8")
        precondition(request.sourceUse.decision == "approved-private-candidates")
        for url in ["http://youtu.be/EAT0nWoEzJ8", "https://evil.test/EAT0nWoEzJ8", "https://user@youtu.be/EAT0nWoEzJ8", "https://youtu.be:444/EAT0nWoEzJ8", "https://youtu.be/bad"] {
            rejects { _ = try VideoCandidateRequest(url: url, displayName: "", approved: true, record: "Original recording") }
        }
        rejects { _ = try VideoCandidateRequest(url: request.videoURL, displayName: "", approved: false, record: "Original recording") }
        rejects { _ = try VideoCandidateRequest(url: request.videoURL, displayName: "", approved: true, record: " ") }
        rejects { _ = try VideoCandidateRequest(url: request.videoURL, displayName: String(repeating: "x", count: 201), approved: true, record: "Original") }
        var receipt: [String: Any] = ["schemaVersion":1,"accepted":true,"videoID":request.videoID,"requestID":request.requestID,"alreadyRequested":false,"format":"f5-reference","identityVerified":false]
        try request.validateReceipt(JSONSerialization.data(withJSONObject: receipt))
        for (key,value) in [("videoID","SYNTHETIC03" as Any),("requestID",UUID().uuidString as Any),("format","rvc" as Any),("accepted",false as Any),("identityVerified",true as Any)] {
            var invalid = receipt; invalid[key] = value
            rejects { try request.validateReceipt(JSONSerialization.data(withJSONObject: invalid)) }
        }
        receipt["alreadyRequested"] = true
        try request.validateReceipt(JSONSerialization.data(withJSONObject: receipt))
        rejects { try request.validateReceipt(Data("<html>Login</html>".utf8)) }
        rejects { try request.validateReceipt(Data(repeating: 32, count: 16_385)) }
        print("Candidate request checks passed: canonical source, explicit affirmation, bounded receipt and correlation")
    }
}
