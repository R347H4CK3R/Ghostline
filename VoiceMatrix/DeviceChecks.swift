import Foundation

struct DeviceVoiceChecks: Codable {
    let version, build, modelRevision: String
    let physicalDevice: Bool
    var checkedProfiles: [String: String]
    var failures: [String: Int]
    var checkedAt: Date
    static let key = "device-voice-checks-v1"
    static var appVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development" }
    static var appBuild: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "development" }
    static var isPhysical: Bool {
        #if targetEnvironment(simulator) || !os(iOS)
        false
        #else
        true
        #endif
    }
    static func load(manifest: VoiceManifest) -> DeviceVoiceChecks {
        if let data = UserDefaults.standard.data(forKey: key), var report = try? JSONDecoder().decode(Self.self, from: data),
           report.version == appVersion, report.build == appBuild, report.modelRevision == manifest.revision, report.physicalDevice == isPhysical {
            report.checkedProfiles = report.checkedProfiles.filter { id, sha in manifest.voices.contains { $0.id == id && $0.sha256 == sha } }
            return report
        }
        return Self(version: appVersion, build: appBuild, modelRevision: manifest.revision, physicalDevice: isPhysical, checkedProfiles: [:], failures: [:], checkedAt: Date())
    }
    func save() { if let data = try? JSONEncoder().encode(self) { UserDefaults.standard.set(data, forKey: Self.key) } }
}
