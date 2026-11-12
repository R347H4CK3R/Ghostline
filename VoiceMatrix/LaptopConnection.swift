import Foundation
import Security

enum LaptopConnection {
    struct Pairing: Decodable { let url: String; let token: String }
    private static let service = "VoiceMatrix.Laptop"
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "pairing"]
    }
    private static var bundledURL: String? {
        guard let file = Bundle.main.url(forResource: "LaptopSettings", withExtension: "json"), let data = try? Data(contentsOf: file), let settings = try? JSONDecoder().decode([String: String].self, from: data) else { return nil }
        return settings["url"]
    }
    static var paired: Bool { (UserDefaults.standard.string(forKey: "laptopURL") ?? bundledURL) != nil }
    static func pair(from file: URL) throws {
        let access = file.startAccessingSecurityScopedResource()
        defer { if access { file.stopAccessingSecurityScopedResource() } }
        let values = try file.resourceValues(forKeys: [.fileSizeKey])
        guard (values.fileSize ?? 0) <= 16_384 else { throw failure("That pairing file is too large.") }
        let pairing = try JSONDecoder().decode(Pairing.self, from: Data(contentsOf: file))
        guard let url = URL(string: pairing.url), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/", pairing.token.utf8.count >= 32 else {
            throw failure("Use the HTTPS pairing file created by your laptop companion.")
        }
        let data = Data(pairing.token.utf8)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query; item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw failure("Pairing could not be saved securely.") }
        } else if status != errSecSuccess { throw failure("Pairing could not be updated securely.") }
        UserDefaults.standard.set(url.absoluteString, forKey: "laptopURL")
    }
    static func send(_ videos: Data) async throws -> String {
        guard let address = UserDefaults.standard.string(forKey: "laptopURL") ?? bundledURL, let root = URL(string: address), root.scheme == "https" else {
            throw failure("Connect your laptop using its pairing file first.")
        }
        var lookup = query; lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var stored: CFTypeRef?
        let found = SecItemCopyMatching(lookup as CFDictionary, &stored)
        let token = found == errSecSuccess ? (stored as? Data).flatMap { String(data: $0, encoding: .utf8) } : nil
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 20
        let session = URLSession(configuration: configuration, delegate: RejectRedirects(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        var request = URLRequest(url: root.appendingPathComponent("queue"))
        request.httpMethod = "POST"; request.httpBody = videos
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        let (_, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw failure("Your laptop returned an unreadable response.") }
        guard response.statusCode == 200 else {
            throw failure(response.statusCode == 401 ? "Connect Tailscale using the same account as your laptop, or import its pairing file." : "Your laptop could not accept the list. Your saved list is unchanged.")
        }
        return "Your laptop accepted the list. This does not mean voice processing is finished."
    }
    static func syncVoices(to folder: URL, previousRevision: String?, syncID: String, progress: @escaping @Sendable (VoiceSyncProgress) async -> Void) async throws -> String? {
        guard let address = UserDefaults.standard.string(forKey: "laptopURL") ?? bundledURL,
              let root = URL(string: address), root.scheme == "https", root.host != nil,
              root.user == nil, root.password == nil, root.query == nil, root.fragment == nil,
              root.path.isEmpty || root.path == "/" else { throw failure("Your laptop connection is unavailable. Saved voices remain offline.") }
        var lookup = query; lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var stored: CFTypeRef?
        let found = SecItemCopyMatching(lookup as CFDictionary, &stored)
        let token = found == errSecSuccess ? (stored as? Data).flatMap { String(data: $0, encoding: .utf8) } : nil
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 120
        let session = URLSession(configuration: configuration, delegate: RejectRedirects(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let pollConfiguration = URLSessionConfiguration.ephemeral
        pollConfiguration.timeoutIntervalForRequest = 3
        pollConfiguration.timeoutIntervalForResource = 5
        let pollSession = URLSession(configuration: pollConfiguration, delegate: RejectRedirects(), delegateQueue: nil)
        let activity = Task {
            var sequence = 0
            var warned = false
            var missingReceipts = 0
            while !Task.isCancelled {
                do {
                    var request = URLRequest(url: root.appendingPathComponent("voice-sync/" + syncID))
                    if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
                    let (stream, response) = try await pollSession.bytes(for: request)
                    if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                        var data = Data()
                        for try await byte in stream {
                            guard data.count < 65_536 else { throw failure("Activity response too large") }
                            data.append(byte)
                        }
                        let snapshot = try JSONDecoder().decode(VoiceSyncRemoteSnapshot.self, from: data)
                        guard snapshot.schemaVersion == 1, snapshot.syncID == syncID else { throw failure("Activity response did not match this sync") }
                        missingReceipts = 0
                        for event in snapshot.newer(than: sequence, for: syncID) {
                            try Task.checkCancellation()
                            if let eventProgress = event.progress { await progress(eventProgress) }
                            sequence = event.sequence
                        }
                    } else {
                        missingReceipts += 1
                        if (response as? HTTPURLResponse)?.statusCode != 404 || missingReceipts >= 3 {
                            throw failure("Laptop activity unavailable")
                        }
                    }
                } catch {
                    if !Task.isCancelled && !warned { await progress(.activityUnavailable); warned = true }
                }
                do { try await Task.sleep(nanoseconds: 1_000_000_000) } catch { return }
            }
        }
        defer { activity.cancel(); pollSession.invalidateAndCancel() }
        let started = Date()
        return try await VoiceFolderSync.bounded(onTimeout: { session.invalidateAndCancel() }) {
          try await VoiceFolderSync.download(to: folder, previousRevision: previousRevision, progress: progress) { path, limit in
            try Task.checkCancellation()
            guard Date().timeIntervalSince(started) < 120 else { throw failure("Voice sync timed out. Your saved voices were kept.") }
            var request = URLRequest(url: root.appendingPathComponent(path))
            request.setValue(syncID, forHTTPHeaderField: "X-VoiceMatrix-Sync-ID")
            if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
            let (stream, response) = try await session.bytes(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 { await progress(.laptopRejected(http.statusCode)) }
            guard let response = response as? HTTPURLResponse, response.statusCode == 200,
                  response.expectedContentLength <= Int64(limit) else { throw failure("Your laptop voice folder is unavailable or changed. Your saved voices were kept.") }
            if path == "voices" { await progress(.laptopResponded) }
            var bytes = Data(); bytes.reserveCapacity(limit)
            for try await byte in stream {
                if bytes.count % 32768 == 0 {
                    try Task.checkCancellation()
                    guard Date().timeIntervalSince(started) < 120 else { throw failure("Voice sync timed out.") }
                }
                guard bytes.count < limit else { throw failure("The laptop sent an oversized voice file.") }
                bytes.append(byte)
                if path != "voices" && bytes.count % 262144 == 0 { await progress(.receiving(bytes.count, limit)) }
            }
            return bytes
          }
        }
    }
    private static func failure(_ message: String) -> NSError { NSError(domain: "VoiceMatrix.Connection", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}

private final class RejectRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
