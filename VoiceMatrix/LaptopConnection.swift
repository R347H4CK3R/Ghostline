import Foundation
import Security

enum LaptopConnection {
    struct Pairing: Decodable { let url: String; let token: String }
    private static let service = "VoiceMatrix.Laptop"
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "pairing"]
    }
    static var paired: Bool { UserDefaults.standard.string(forKey: "laptopURL") != nil }
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
        guard let address = UserDefaults.standard.string(forKey: "laptopURL"), let root = URL(string: address), root.scheme == "https" else {
            throw failure("Connect your laptop using its pairing file first.")
        }
        var lookup = query; lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var stored: CFTypeRef?
        guard SecItemCopyMatching(lookup as CFDictionary, &stored) == errSecSuccess,
              let data = stored as? Data, let token = String(data: data, encoding: .utf8) else { throw failure("Reconnect your laptop to restore pairing.") }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 20
        let session = URLSession(configuration: configuration, delegate: RejectRedirects(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        var request = URLRequest(url: root.appendingPathComponent("queue"))
        request.httpMethod = "POST"; request.httpBody = videos
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw failure("Your laptop returned an unreadable response.") }
        guard response.statusCode == 200 else {
            throw failure(response.statusCode == 401 ? "Pairing expired. Reconnect your laptop." : "Your laptop could not accept the list. Your saved list is unchanged.")
        }
        return "Your laptop accepted the list. This does not mean voice processing is finished."
    }
    private static func failure(_ message: String) -> NSError { NSError(domain: "VoiceMatrix.Connection", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}

private final class RejectRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
