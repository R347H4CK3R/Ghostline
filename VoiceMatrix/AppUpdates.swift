import SwiftUI
import UIKit

struct AppUpdate: Codable, Equatable {
    let version: String
    let buildVersion: String?
    let downloadURL: URL
    let localizedDescription: String?
    let minOSVersion: String?
    let size: Int64
    var build: String { buildVersion ?? "0" }
    var label: String { version + " (" + build + ")" }
}

enum UpdateCatalog {
    static let feedURL = URL(string: "https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json")!
    private struct Feed: Decodable {
        struct App: Decodable { let bundleIdentifier: String; let versions: [AppUpdate] }
        let apps: [App]
    }
    static func components(_ value: String) -> [Int]? {
        let parts = value.split(separator: ".", omittingEmptySubsequences: false)
        guard !parts.isEmpty, parts.count <= 4 else { return nil }
        var numbers: [Int] = []
        for part in parts {
            guard !part.isEmpty, part.allSatisfy({ $0.isASCII && $0.isNumber }),
                  let number = Int(part), number >= 0 else { return nil }
            numbers.append(number)
        }
        return numbers
    }
    static func compare(_ lhs: String, _ rhs: String) -> ComparisonResult {
        let a = components(lhs) ?? [], b = components(rhs) ?? []
        for i in 0..<max(a.count, b.count) {
            let x = i < a.count ? a[i] : 0, y = i < b.count ? b[i] : 0
            if x != y { return x < y ? .orderedAscending : .orderedDescending }
        }
        return .orderedSame
    }
    static func allowedDownload(_ url: URL) -> Bool {
        guard let c = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return false }
        return c.scheme == "https" && c.host == "github.com" && c.user == nil && c.password == nil &&
            c.port == nil && c.query == nil && c.fragment == nil &&
            c.path.hasPrefix("/R347H4CK3R/Ghostline/releases/download/") &&
            !c.path.split(separator: "/").contains("..") && c.path.hasSuffix(".ipa")
    }
    static func latest(_ data: Data, installedVersion: String, installedBuild: String) throws -> AppUpdate? {
        guard data.count <= 1_048_576, components(installedVersion) != nil,
              components(installedBuild) != nil else { throw UpdateError.invalidFeed }
        let feed = try JSONDecoder().decode(Feed.self, from: data)
        let matches = feed.apps.filter { $0.bundleIdentifier == "com.voicematrix.app" }
        guard matches.count == 1 else { throw UpdateError.invalidFeed }
        let versions = matches[0].versions
        guard !versions.isEmpty, versions.allSatisfy({
            components($0.version) != nil && components($0.build) != nil &&
            ($0.minOSVersion == nil || components($0.minOSVersion!) != nil) &&
            $0.size > 0 && $0.size <= 2_000_000_000 && allowedDownload($0.downloadURL)
        }) else { throw UpdateError.invalidFeed }
        return versions.filter {
            compare($0.version, installedVersion) == .orderedDescending ||
            (compare($0.version, installedVersion) == .orderedSame && compare($0.build, installedBuild) == .orderedDescending)
        }.max {
            let versionOrder = compare($0.version, $1.version)
            return versionOrder == .orderedSame ? compare($0.build, $1.build) == .orderedAscending : versionOrder == .orderedAscending
        }
    }
}

enum UpdateError: LocalizedError {
    case invalidFeed, server, wrongSize
    var errorDescription: String? {
        switch self {
        case .invalidFeed: return "The update listing could not be verified. Try again later."
        case .server: return "The update server did not return a usable response."
        case .wrongSize: return "The download was incomplete. Download it again before installing."
        }
    }
}

@MainActor final class AppUpdater: ObservableObject {
    @Published private(set) var candidate: AppUpdate?
    @Published private(set) var downloaded: URL?
    @Published private(set) var busy = false
    @Published private(set) var message = "Check for a published VoiceMatrix update."
    private var task: Task<Void, Never>?
    let installedVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    let installedBuild = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "0"
    var compatible: Bool {
        guard let minimum = candidate?.minOSVersion else { return true }
        let os = ProcessInfo.processInfo.operatingSystemVersion
        return UpdateCatalog.compare("\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)", minimum) != .orderedAscending
    }
    func check() {
        guard !busy else { return }
        busy = true; candidate = nil; downloaded = nil; message = "Checking for updates…"
        task = Task {
            defer { busy = false; task = nil }
            do {
                var request = URLRequest(url: UpdateCatalog.feedURL)
                request.cachePolicy = .reloadIgnoringLocalCacheData
                request.timeoutInterval = 30
                let (bytes, response) = try await URLSession.shared.bytes(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.server }
                var data = Data()
                for try await byte in bytes {
                    guard data.count < 1_048_576 else { throw UpdateError.invalidFeed }
                    data.append(byte)
                }
                try Task.checkCancellation()
                candidate = try UpdateCatalog.latest(data, installedVersion: installedVersion, installedBuild: installedBuild)
                message = candidate == nil ? "No newer published version is available." :
                    (compatible ? "An update is available." : "This update requires a newer iOS version.")
            } catch {
                message = Task.isCancelled ? "Update check cancelled." : "Could not check for updates. " + error.localizedDescription
            }
        }
    }
    func download() {
        guard !busy, compatible, let candidate else { return }
        busy = true; downloaded = nil; message = "Downloading update… Keep VoiceMatrix open."
        task = Task {
            defer { busy = false; task = nil }
            do {
                var request = URLRequest(url: candidate.downloadURL)
                request.timeoutInterval = 300
                let (temporary, response) = try await URLSession.shared.download(for: request)
                defer { try? FileManager.default.removeItem(at: temporary) }
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.server }
                let values = try temporary.resourceValues(forKeys: [.fileSizeKey])
                guard Int64(values.fileSize ?? 0) == candidate.size else { throw UpdateError.wrongSize }
                try Task.checkCancellation()
                let folder = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("AppUpdates", isDirectory: true)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let target = folder.appendingPathComponent("VoiceMatrix-update.ipa")
                if FileManager.default.fileExists(atPath: target.path) { try FileManager.default.removeItem(at: target) }
                try FileManager.default.moveItem(at: temporary, to: target)
                downloaded = target
                message = "Download complete. Share the IPA to Strata, then replace the existing VoiceMatrix app."
            } catch {
                message = Task.isCancelled ? "Download cancelled. Your voices and recordings were kept." : "Update download failed. " + error.localizedDescription
            }
        }
    }
    func cancel() { task?.cancel() }
    func copyLinkAndOpenHost() {
        guard let candidate, compatible else { return }
        UIPasteboard.general.url = candidate.downloadURL
        message = "Update link copied. In Strata, use Install from URL, paste the link, and replace VoiceMatrix. Keep its existing data container."
        // Strata rejects install:// requests while this guest is running.
        // Switching to its UI is supported; the user completes installation there.
        UIApplication.shared.open(URL(string: "livecontainer://livecontainer-launch?bundle-name=ui")!, options: [:]) { opened in
            Task { @MainActor in
                if !opened { self.message = "Update link copied. Open Strata manually, use Install from URL, and replace the existing VoiceMatrix app." }
            }
        }
    }
}

struct AppUpdatesView: View {
    @StateObject private var updater = AppUpdater()
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var library: CharacterLibrary
    @EnvironmentObject private var studio: SpeechStudio
    private var workInProgress: Bool { library.busy || library.syncing || studio.busy || audio.microphoneInUse || audio.processingInUse || audio.playing != nil }
    var body: some View {
        Form {
            Section("Installed version") { Text(updater.installedVersion + " (" + updater.installedBuild + ")") }
            Section("Updates") {
                Button("Check for Updates") { updater.check() }.disabled(updater.busy)
                Text(updater.message).accessibilityIdentifier("update-status")
                if updater.busy {
                    ProgressView()
                    Button("Cancel", role: .cancel) { updater.cancel() }
                }
                if let update = updater.candidate {
                    Text("Available: " + update.label).font(.headline)
                    Text(update.localizedDescription ?? "")
                    Text(ByteCountFormatter.string(fromByteCount: update.size, countStyle: .file))
                    if let minimum = update.minOSVersion { Text("Requires iOS " + minimum).font(.caption) }
                    Button("Download Update") { updater.download() }.disabled(updater.busy || !updater.compatible || workInProgress)
                    if let downloaded = updater.downloaded {
                        ShareLink(item: downloaded) { Label("Share Update to Strata", systemImage: "square.and.arrow.up") }
                            .disabled(workInProgress || updater.busy)
                    }
                    Button("Copy Update Link & Open Strata") { updater.copyLinkAndOpenHost() }
                        .disabled(updater.busy || !updater.compatible || workInProgress)
                }
            }
            Section("Install without losing your voices") {
                Text("Strata must finish installation after you leave VoiceMatrix. Choose the existing VoiceMatrix app to replace, and keep its existing data container. Do not delete the app first or install a second copy.")
                Text("Your imported voices, saved recordings and pairing settings stay in the existing container. VoiceMatrix does not upload them when checking or downloading updates.")
                if workInProgress { Text("Finish recording, playback, speech or voice sync before installing an update.").foregroundStyle(.orange) }
            }
        }.navigationTitle("App Updates")
        .onDisappear { updater.cancel() }
    }
}
