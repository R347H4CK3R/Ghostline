import Foundation
@main struct Checks {
    static func main() {
        precondition(LocalStudioEvidence.wordErrorRate(expected: "I found a strange device near the portal.", actual: "Found a strange device near the portal.") > 0.1)
        precondition(LocalStudioEvidence.wordErrorRate(expected: "HELLO world!", actual: "hello world") == 0)
        precondition(!LocalStudioEvidence.usableTranscript("♪ music is playing"))
        precondition(LocalStudioEvidence.windows(duration: .nan).isEmpty)
        for duration in [3.0, 7.5, 17, 1800] {
            let windows = LocalStudioEvidence.windows(duration: duration)
            precondition(!windows.isEmpty && windows.count <= 300)
            precondition(windows.allSatisfy { $0.start >= 0 && $0.seconds >= 3 && $0.seconds <= 8 && $0.start + $0.seconds <= duration })
        }
        print("Native local evidence checks passed; no model inference was performed")
    }
}
