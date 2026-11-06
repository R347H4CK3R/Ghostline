import Foundation

@main
struct GhostlineHTTPHeaderBufferTests {
    private static let request = Data("GET /index.html HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".utf8)

    static func main() {
        var parser = GhostlineHTTPHeaderBuffer()
        for (index, byte) in request.enumerated() {
            let outcome = parser.append(Data([byte]), streamEnded: false)
            if index + 1 == request.count {
                guard case .ready(let value) = outcome else { fatalError("Final fragment was not recognized") }
                precondition(value == request)
            } else if case .pending = outcome {
                // Fragmented headers are normal TCP traffic.
            } else {
                fatalError("Rejected valid fragmented HTTP headers at offset \(index)")
            }
        }

        var mixed = GhostlineHTTPHeaderBuffer()
        let padded = request + Data([0, 255, 42, 0])
        guard case .ready(let header) = mixed.append(padded, streamEnded: false) else {
            fatalError("Complete header with trailing bytes was rejected")
        }
        precondition(header == request)

        var tooLarge = GhostlineHTTPHeaderBuffer()
        guard case .tooLarge = tooLarge.append(Data(repeating: 65, count: GhostlineHTTPHeaderBuffer.maximumBytes + 1), streamEnded: false) else {
            fatalError("Oversized request was not rejected")
        }

        var incomplete = GhostlineHTTPHeaderBuffer()
        guard case .invalid = incomplete.append(Data("GET / HT".utf8), streamEnded: true) else {
            fatalError("Closed partial request was accepted")
        }

        var exactlyBounded = GhostlineHTTPHeaderBuffer()
        let head = Data(repeating: 65, count: GhostlineHTTPHeaderBuffer.maximumBytes - 4) + Data("\r\n\r\n".utf8)
        guard case .ready(let accepted) = exactlyBounded.append(head, streamEnded: false) else {
            fatalError("Exactly bounded request should be accepted for parsing")
        }
        precondition(accepted.count == GhostlineHTTPHeaderBuffer.maximumBytes)

        let csp = GhostlineRVCNetworkPolicy.contentSecurityPolicy
        let directives = csp.split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) }
        precondition(directives.contains("connect-src 'self' blob: data:"))
        precondition(directives.contains("worker-src 'self' blob:"))
        precondition(directives.contains("object-src 'none'"))
        precondition(directives.contains("frame-src 'none'"))
        precondition(directives.contains("form-action 'none'"))
        precondition(!csp.contains("https:") && !csp.contains("http:") && !csp.contains("*"))
        print("PASS offline-only CSP source directives; device WebKit enforcement remains unverified.")
        print("PASS fragmented, bytewise, body-suffix, oversized, incomplete and bounded HTTP headers.")
        print("HTTP framing tests are not proof of iPhone/Strata inference or voice identity.")
    }
}
