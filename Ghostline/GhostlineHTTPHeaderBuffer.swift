import Foundation

/// Bounded TCP/HTTP request-header framing for the local offline RVC server.
/// A read() callback may deliver only one byte of a request line; process the
/// request only after the complete CRLF-CRLF terminator is present.
struct GhostlineHTTPHeaderBuffer: Sendable {
    enum Outcome {
        case pending
        case ready(Data)
        case invalid
        case tooLarge
    }

    private var buffer = Data()
    private static let terminator = Data("\r\n\r\n".utf8)
    static let maximumBytes = 16_384

    mutating func append(_ fragment: Data, streamEnded: Bool) -> Outcome {
        guard !fragment.isEmpty else { return .invalid }
        guard fragment.count <= Self.maximumBytes,
              buffer.count <= Self.maximumBytes - fragment.count else {
            return .tooLarge
        }
        buffer.append(fragment)
        if let end = buffer.range(of: Self.terminator) {
            // Never interpret any extra request-body bytes as part of the
            // request line or headers (GET/HEAD handlers do not accept bodies).
            return .ready(Data(buffer[..<end.upperBound]))
        }
        return streamEnded ? .invalid : .pending
    }
}


// Defense-in-depth: navigation policy does not restrict fetch(), worker
// scripts, CSS or audio resources. The document CSP disallows all remote
// network destinations while retaining local WebAssembly execution.
enum GhostlineRVCNetworkPolicy {
    static let contentSecurityPolicy =
        "default-src 'self'; connect-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; font-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
}
