import Foundation
import CryptoKit
import Security

/// Each instance captures one paired origin and credential. An in-flight request
/// must never migrate to a different laptop after pairing settings are changed.
struct RVCOnlineConnection: RVCOnlineCatalogTransport, Sendable {
    private let endpoint: RVCOnlineEndpoint
    private let token: String?

    init(root: URL, token: String?) throws {
        endpoint = try RVCOnlineEndpoint(root: root)
        if let token {
            guard (32...4096).contains(token.utf8.count),
                  token.utf8.allSatisfy({ (33...126).contains($0) }) else { throw RVCOnlineError.invalidConnection }
        }
        self.token = token
    }

    static func paired() throws -> Self {
        guard let address = UserDefaults.standard.string(forKey: "laptopURL") ?? LaptopConnection.bundledURL,
              let root = URL(string: address) else { throw RVCOnlineError.invalidConnection }
        var lookup = LaptopConnection.query
        lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var stored: CFTypeRef?
        let status = SecItemCopyMatching(lookup as CFDictionary, &stored)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw RVCOnlineError.invalidConnection }
        let token: String?
        if status == errSecSuccess {
            guard let data = stored as? Data, let value = String(data: data, encoding: .utf8) else { throw RVCOnlineError.invalidConnection }
            token = value
        } else { token = nil } // Existing same-owner Tailscale authentication remains supported.
        return try Self(root: root, token: token)
    }

    static func request(model: RVCOnlineModel, wav: Data, id: UUID = UUID()) throws -> RVCOnlineRequest {
        _ = try RVCOnlineWAV.inspect(wav)
        return try RVCOnlineRequest(model: model, wav: wav, inputSHA256: digest(wav), id: id)
    }

    func catalog() async throws -> RVCOnlineCatalog {
        let response = try await exchange(endpoint.catalog, limit: RVCOnlineCatalog.byteLimit)
        return try RVCOnlineCatalog.decode(response.data)
    }

    func submit(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        try Task.checkCancellation()
        // Refresh before upload so a selected model cannot silently resolve to new
        // weights. Hashes/revision in the request also guard the race server-side.
        let catalog = try await catalog()
        guard catalog.onlineConversionAvailable else { throw RVCOnlineError.unavailable }
        guard catalog.models.contains(where: {
            $0.id == request.modelID && $0.modelSHA256 == request.modelSHA256 &&
            $0.indexSHA256 == request.indexSHA256 && $0.revision == request.revision
        }) else { throw RVCOnlineError.modelChanged }
        guard let wav = Data(base64Encoded: request.wavBase64), wav.base64EncodedString() == request.wavBase64,
              Self.digest(wav) == request.inputSHA256 else { throw RVCOnlineError.invalidRequest }
        _ = try RVCOnlineWAV.inspect(wav)
        let body = try request.encodedBody()
        let response = try await exchange(endpoint.conversions, method: "POST", body: body,
                                          limit: RVCOnlineSnapshot.byteLimit, codes: [202])
        return try RVCOnlineSnapshot.decode(response.data, for: request)
    }

    func status(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        let response = try await exchange(endpoint.job(request.requestID), limit: RVCOnlineSnapshot.byteLimit)
        return try RVCOnlineSnapshot.decode(response.data, for: request)
    }

    func cancel(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        let response = try await exchange(endpoint.job(request.requestID).appendingPathComponent("cancel"),
                                          method: "POST", body: Data("{}".utf8), limit: RVCOnlineSnapshot.byteLimit, codes: [200, 202])
        return try RVCOnlineSnapshot.decode(response.data, for: request)
    }

    func result(_ request: RVCOnlineRequest, snapshot: RVCOnlineSnapshot) async throws -> Data {
        try snapshot.validate(for: request)
        guard snapshot.status == .succeeded, let expected = snapshot.result else { throw RVCOnlineError.invalidResponse }
        let response = try await exchange(endpoint.job(request.requestID).appendingPathComponent("result"),
                                          limit: expected.bytes, audio: true)
        try Self.validateResult(response.data, headerSHA256: response.sha256, expected: expected)
        return response.data
    }

    static func validateResult(_ data: Data, headerSHA256: String?, expected: RVCOnlineSnapshot.Result) throws {
        try expected.validate()
        guard data.count == expected.bytes, headerSHA256 == expected.sha256,
              digest(data) == expected.sha256 else { throw RVCOnlineError.invalidAudio }
        let audio = try RVCOnlineWAV.inspect(data)
        guard audio.sampleRate == expected.sampleRate,
              abs(audio.seconds - expected.seconds) <= 1.0 / Double(audio.sampleRate) else { throw RVCOnlineError.invalidAudio }
    }

    private static func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private struct Response: Sendable { let data: Data; let sha256: String? }
    private func exchange(_ url: URL, method: String = "GET", body: Data? = nil,
                          limit: Int, codes: Set<Int> = [200], audio: Bool = false) async throws -> Response {
        try Task.checkCancellation()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = method == "POST" ? 60 : 30
        configuration.waitsForConnectivity = false
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        configuration.httpShouldSetCookies = false
        configuration.urlCredentialStorage = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: configuration, delegate: RVCOnlineRejectRedirects(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        var request = URLRequest(url: url)
        request.httpMethod = method; request.httpBody = body
        request.setValue(audio ? "audio/wav" : "application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        // Capture the immutable request explicitly for Swift concurrency checks.
        let prepared = request
        return try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            let (stream, response) = try await session.bytes(for: prepared)
            guard let http = response as? HTTPURLResponse, http.url == url else { throw RVCOnlineError.invalidResponse }
            guard codes.contains(http.statusCode) else {
                switch http.statusCode {
                case 401, 403: throw RVCOnlineError.authenticationRequired
                case 409: throw RVCOnlineError.modelChanged
                default: throw RVCOnlineError.httpStatus(http.statusCode)
                }
            }
            let media = http.mimeType?.lowercased()
            guard media == (audio ? "audio/wav" : "application/json"),
                  http.expectedContentLength <= Int64(limit) else { throw RVCOnlineError.invalidResponse }
            var data = Data()
            for try await byte in stream {
                if data.count % 16_384 == 0 { try Task.checkCancellation() }
                guard data.count < limit else { throw RVCOnlineError.invalidResponse }
                data.append(byte)
            }
            try Task.checkCancellation()
            if http.expectedContentLength >= 0, http.expectedContentLength != Int64(data.count) { throw RVCOnlineError.invalidResponse }
            return Response(data: data, sha256: http.value(forHTTPHeaderField: "X-Content-SHA256"))
        }, onCancel: { session.invalidateAndCancel() })
    }
}

private final class RVCOnlineRejectRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
