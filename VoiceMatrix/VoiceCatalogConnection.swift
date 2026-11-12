import Foundation
import Security

extension LaptopConnection {
    static func voiceCatalog(syncID: String, progress: @escaping @Sendable (VoiceSyncProgress) async -> Void) async throws -> RemoteVoiceCatalog {
        try await withVoiceTransport(seconds: 30, syncID: syncID, progress: progress) { session, root, token in
            let data = try await fetchVoice("voices", limit: RemoteVoiceCatalog.byteLimit, session: session, root: root, token: token, syncID: syncID, progress: progress)
            let catalog = try RemoteVoiceCatalog.decode(data)
            await progress(.catalogValidated(catalog.files.count, catalog.files.reduce(0) { $0 + $1.bytes }))
            return catalog
        }
    }
    static func downloadVoice(_ expected: CharacterReference, to folder: URL, syncID: String, progress: @escaping @Sendable (VoiceSyncProgress) async -> Void) async throws -> RemoteVoiceCatalog {
        try await withVoiceTransport(seconds: 120, syncID: syncID, progress: progress) { session, root, token in
            // Establish a current server snapshot after reconnect/restart. Never silently
            // download a changed reference under the name the owner selected earlier.
            let data = try await fetchVoice("voices", limit: RemoteVoiceCatalog.byteLimit, session: session, root: root, token: token, syncID: syncID, progress: progress)
            let catalog = try RemoteVoiceCatalog.decode(data)
            guard catalog.voices.first(where: { $0.id == expected.id }) == expected else { throw RemoteVoiceCatalog.invalid() }
            try await catalog.download(id: expected.id, to: folder, progress: progress) { path, limit in
                try await fetchVoice(path, limit: limit, session: session, root: root, token: token, syncID: syncID, progress: progress)
            }
            return catalog
        }
    }
    private static func withVoiceTransport<T: Sendable>(seconds: Double, syncID: String, progress: @escaping @Sendable (VoiceSyncProgress) async -> Void, operation: @escaping @Sendable (URLSession, URL, String?) async throws -> T) async throws -> T {
        guard let address = UserDefaults.standard.string(forKey: "laptopURL") ?? bundledURL,
              let root = URL(string: address), root.scheme == "https", root.host != nil,
              root.user == nil, root.password == nil, root.query == nil, root.fragment == nil,
              root.path.isEmpty || root.path == "/" else { throw RemoteVoiceCatalog.invalid() }
        var lookup = query; lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var stored: CFTypeRef?
        let found = SecItemCopyMatching(lookup as CFDictionary, &stored)
        let token = found == errSecSuccess ? (stored as? Data).flatMap { String(data: $0, encoding: .utf8) } : nil
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = seconds
        configuration.waitsForConnectivity = false
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: configuration, delegate: VoiceCatalogRejectRedirects(), delegateQueue: nil)
        let pollConfiguration = URLSessionConfiguration.ephemeral
        pollConfiguration.timeoutIntervalForRequest = 3
        pollConfiguration.timeoutIntervalForResource = 5
        pollConfiguration.urlCache = nil
        let pollSession = URLSession(configuration: pollConfiguration, delegate: VoiceCatalogRejectRedirects(), delegateQueue: nil)
        let activity = Task {
            var sequence = 0, missingReceipts = 0
            var warned = false
            while !Task.isCancelled {
                do {
                    let endpoint = root.appendingPathComponent("voice-sync/" + syncID)
                    var request = URLRequest(url: endpoint)
                    if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
                    let (stream, response) = try await pollSession.bytes(for: request)
                    if let http = response as? HTTPURLResponse, http.statusCode == 200, http.url == endpoint,
                       http.expectedContentLength <= 65_536 {
                        var data = Data()
                        for try await byte in stream {
                            try Task.checkCancellation()
                            guard data.count < 65_536 else { throw RemoteVoiceCatalog.invalid() }
                            data.append(byte)
                        }
                        let snapshot = try JSONDecoder().decode(VoiceSyncRemoteSnapshot.self, from: data)
                        guard snapshot.schemaVersion == 1, snapshot.syncID == syncID else { throw RemoteVoiceCatalog.invalid() }
                        missingReceipts = 0
                        for event in snapshot.newer(than: sequence, for: syncID) {
                            try Task.checkCancellation()
                            if let update = event.progress { await progress(update) }
                            sequence = event.sequence
                        }
                    } else {
                        missingReceipts += 1
                        if (response as? HTTPURLResponse)?.statusCode != 404 || missingReceipts >= 3 { throw RemoteVoiceCatalog.invalid() }
                    }
                } catch {
                    if !Task.isCancelled && !warned { await progress(.activityUnavailable); warned = true }
                }
                do { try await Task.sleep(nanoseconds: 1_000_000_000) } catch { return }
            }
        }
        defer { activity.cancel(); pollSession.invalidateAndCancel(); session.invalidateAndCancel() }
        return try await withTaskCancellationHandler(operation: {
            try await VoiceFolderSync.bounded(seconds: seconds, onTimeout: { session.invalidateAndCancel() }) {
                try Task.checkCancellation()
                return try await operation(session, root, token)
            }
        }, onCancel: { activity.cancel(); pollSession.invalidateAndCancel(); session.invalidateAndCancel() })
    }
    private static func fetchVoice(_ path: String, limit: Int, session: URLSession, root: URL, token: String?, syncID: String, progress: @Sendable (VoiceSyncProgress) async -> Void) async throws -> Data {
        try Task.checkCancellation()
        let endpoint = root.appendingPathComponent(path)
        var request = URLRequest(url: endpoint)
        request.setValue(syncID, forHTTPHeaderField: "X-VoiceMatrix-Sync-ID")
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        let (stream, response) = try await session.bytes(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 { await progress(.laptopRejected(http.statusCode)) }
        guard let response = response as? HTTPURLResponse, response.statusCode == 200,
              response.url == endpoint, response.expectedContentLength <= Int64(limit) else { throw RemoteVoiceCatalog.invalid() }
        if path == "voices" { await progress(.laptopResponded) }
        var data = Data(); data.reserveCapacity(limit)
        for try await byte in stream {
            if data.count % 32_768 == 0 { try Task.checkCancellation() }
            guard data.count < limit else { throw RemoteVoiceCatalog.invalid() }
            data.append(byte)
            if path != "voices", data.count % 262_144 == 0 { await progress(.receiving(data.count, limit)) }
        }
        try Task.checkCancellation()
        return data
    }
}

private final class VoiceCatalogRejectRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
