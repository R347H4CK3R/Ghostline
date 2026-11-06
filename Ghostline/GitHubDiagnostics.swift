import SwiftUI
import Foundation
import Security

// Uploads only allowlisted error codes and generic platform metadata.
// NEVER send raw NSError descriptions, filenames, voice text, audio, tokens,
// model identities or stack traces to a public GitHub issue.
private struct GhostlineDiagnostic: Codable, Identifiable {
    let id: UUID
    let whenUTC: String
    let subsystem: String
    let code: String
    let appVersion: String
    let osMajor: String
}

@MainActor
final class GhostlineDiagnostics: ObservableObject {
    static let shared = GhostlineDiagnostics()
    @Published private(set) var entries: [GhostlineDiagnostic] = []
    @Published var enabled: Bool {
        didSet { UserDefaults.standard.set(enabled, forKey: "ghostline.diagnostics.consent") }
    }
    @Published private(set) var status: String = "Local-only error diagnostics"
    @Published private(set) var sending = false
    @Published private(set) var lastSend: Date?
    private let consentKey = "ghostline.diagnostics.consent"
    private let keychainAccount = "ghostline-diagnostics-issues-write"
    private let maxStored = 80
    private let fileURL: URL

    private init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                             in: .userDomainMask)[0]
        fileURL = base.appendingPathComponent("ghostline-safe-diagnostics.json")
        enabled = UserDefaults.standard.bool(forKey: consentKey)
        if let data = try? Data(contentsOf: fileURL),
           let loaded = try? JSONDecoder().decode([GhostlineDiagnostic].self, from: data) {
            entries = Array(loaded.prefix(maxStored))
        }
    }

    var hasToken: Bool { readToken() != nil }

    func saveToken(_ token: String) -> Bool {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 20, trimmed.count <= 300,
              trimmed.rangeOfCharacter(from: .whitespacesAndNewlines) == nil else {
            status = "A fine-grained GitHub token with Issues: write is required."
            return false
        }
        let base = [kSecClass as String: kSecClassGenericPassword,
                    kSecAttrService as String: "com.ghostline.studio.diagnostics",
                    kSecAttrAccount as String: keychainAccount] as [String: Any]
        SecItemDelete(base as CFDictionary)
        var add = base
        add[kSecValueData as String] = Data(trimmed.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let code = SecItemAdd(add as CFDictionary, nil)
        status = code == errSecSuccess ? "Private GitHub token stored in iOS Keychain." :
            "Unable to store token. GitHub reporting remains disabled."
        return code == errSecSuccess
    }

    func disconnect() {
        let query = [kSecClass as String: kSecClassGenericPassword,
                     kSecAttrService as String: "com.ghostline.studio.diagnostics",
                     kSecAttrAccount as String: keychainAccount] as [String: Any]
        SecItemDelete(query as CFDictionary)
        enabled = false
        status = "GitHub disconnected. Remaining events are local only."
    }

    private func readToken() -> String? {
        let query = [kSecClass as String: kSecClassGenericPassword,
                     kSecAttrService as String: "com.ghostline.studio.diagnostics",
                     kSecAttrAccount as String: keychainAccount,
                     kSecReturnData as String: true,
                     kSecMatchLimit as String: kSecMatchLimitOne] as [String: Any]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    // No user-controlled text enters the uploaded event; unknown categories are
    // converted to generic, preventing private paths or model names escaping.
    func record(_ subsystem: String, _ code: String) {
        let allowedSubsystems: Set<String> = ["community", "piper", "rvc", "kokoro", "pockettts", "app"]
        let allowedCodes: Set<String> = [
            "file_import_failed", "file_picker_failed", "model_download_failed",
            "model_checksum_failed", "model_load_failed", "audio_generation_failed",
            "audio_playback_failed", "index_validation_failed", "runtime_failed"
        ]
        let cleanSubsystem = allowedSubsystems.contains(subsystem) ? subsystem : "app"
        let cleanCode = allowedCodes.contains(code) ? code : "runtime_failed"
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        let major = String(ProcessInfo.processInfo.operatingSystemVersion.majorVersion)
        let day = ISO8601DateFormatter().string(from: Date())
        let event = GhostlineDiagnostic(id: UUID(), whenUTC: day,
                                        subsystem: cleanSubsystem, code: cleanCode,
                                        appVersion: version, osMajor: major)
        entries.insert(event, at: 0)
        entries = Array(entries.prefix(maxStored))
        persist()
        if enabled && hasToken {
            Task { await self.sendQueuedIfAllowed() }
        }
    }

    private func persist() {
        do {
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONEncoder().encode(entries).write(to: fileURL, options: .atomic)
        } catch {
            status = "Local diagnostic storage unavailable."
        }
    }

    func exportURL() -> URL? { FileManager.default.fileExists(atPath: fileURL.path) ? fileURL : nil }

    func clearLocalEvents() {
        entries = []
        persist()
        status = "Local diagnostic events cleared."
    }

    func sendQueuedIfAllowed(force: Bool = false) async {
        guard !sending, enabled else { return }
        guard let token = readToken() else {
            status = "Connect GitHub before enabling automatic error reports."
            return
        }
        guard !entries.isEmpty else { status = "No unsent errors."; return }
        if !force, let lastSend, Date().timeIntervalSince(lastSend) < 300 { return }
        sending = true
        defer { sending = false }
        // Batch only a few coded events to avoid spam or public data leakage.
        let events = Array(entries.suffix(10))
        let body = events.map {
            "- \($0.whenUTC) | \($0.subsystem) | \($0.code) | app \($0.appVersion) | iOS \($0.osMajor)"
        }.joined(separator: "\n")
        let issue = [
            "title": "[Ghostline diagnostics] \(events.count) sanitized app error(s)",
            "body": "Automatically generated with user consent. No model paths, text, audio, identity data or raw error descriptions.\n\n" + body
        ]
        guard let url = URL(string: "https://api.github.com/repos/R347H4CK3R/Ghostline/issues"),
              let payload = try? JSONSerialization.data(withJSONObject: issue)
        else { status = "Cannot form GitHub diagnostic request."; return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 25
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.httpBody = payload
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                status = "Diagnostic delivery failed: invalid response."; return
            }
            guard http.statusCode == 201 else {
                status = "GitHub rejected report (HTTP \(http.statusCode)). Events retained locally."
                return
            }
            let completed = Set(events.map(\.id))
            entries.removeAll { completed.contains($0.id) }
            persist()
            lastSend = Date()
            status = "Sanitized diagnostic issue created. Events removed from local queue."
        } catch {
            status = "Network unavailable. Diagnostic events remain queued locally."
        }
    }
}

struct GhostlineDiagnosticsView: View {
    @ObservedObject private var diagnostics = GhostlineDiagnostics.shared
    @State private var token = ""
    var body: some View {
        Form {
            Section("Live diagnostics") {
                Toggle("Automatically report sanitized errors to GitHub", isOn: $diagnostics.enabled)
                Text("Reports are sent while Ghostline is running and a network connection is available. Offline events stay on the device.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Only a fixed error category, time, app version and iOS major version are included. GitHub issues in this repository may be publicly visible.")
                    .font(.caption).foregroundStyle(.orange)
            }
            Section("GitHub connection") {
                if diagnostics.hasToken {
                    Label("Token stored in iOS Keychain", systemImage: "lock.shield")
                    Button("Disconnect", role: .destructive) { diagnostics.disconnect() }
                } else {
                    SecureField("Fine-grained token (Issues: write)", text: $token)
                        .textContentType(.password)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Save private GitHub token") {
                        if diagnostics.saveToken(token) { token = "" }
                    }.disabled(token.isEmpty)
                    Text("Create a fine-grained token scoped only to R347H4CK3R/Ghostline with Issues write permission. Never embed tokens in an IPA.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Pending events") {
                Text("\(diagnostics.entries.count) sanitized error(s) queued")
                Button("Send queued errors now") {
                    Task { await diagnostics.sendQueuedIfAllowed(force: true) }
                }.disabled(diagnostics.entries.isEmpty || !diagnostics.hasToken ||
                            !diagnostics.enabled || diagnostics.sending)
                if diagnostics.sending { ProgressView("Sending coded errors…") }
                Text(diagnostics.status).font(.caption).foregroundStyle(.secondary)
                if let file = diagnostics.exportURL() {
                    ShareLink(item: file) { Label("Export local diagnostic JSON", systemImage: "square.and.arrow.up") }
                }
                Button("Clear local errors", role: .destructive) { diagnostics.clearLocalEvents() }
                    .disabled(diagnostics.entries.isEmpty)
            }
        }
        .navigationTitle("GitHub Diagnostics")
    }
}
