import Foundation
import CryptoKit

struct CharacterReference: Codable, Identifiable, Equatable {
    let id, name, source, permission, referenceText: String
    let schemaVersion: Int
    let kind, engine, referenceFile, referenceSHA256: String
    let trainedModel: Bool
    let categories: [String]
    let referenceBytes: Int
    let seconds: Double
}

enum CharacterImportError: LocalizedError {
    case invalid(String)
    var errorDescription: String? {
        switch self { case .invalid(let reason): return "This voice folder could not be imported. " + reason }
    }
}

// Immutable revision directories and one atomic index commit keep the old library usable
// if validation, copying, cancellation, or the external folder fails during a refresh.
actor CharacterFolderStore {
    private struct Collection: Codable {
        struct Entry: Codable { let id, folder: String }
        let schemaVersion: Int
        let voices: [Entry]
    }
    private let root: URL
    private let fm = FileManager.default
    init(root: URL) { self.root = root }
    private static func safeID(_ value: String) -> Bool {
        value.range(of: "^[a-z0-9_-]{1,100}$", options: .regularExpression) != nil
    }
    private func regular(_ url: URL, limit: Int) throws -> Data {
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, size >= 0, size <= limit else {
            throw CharacterImportError.invalid("A file is missing, linked elsewhere, or too large.")
        }
        let data = try Data(contentsOf: url)
        guard data.count == size else { throw CharacterImportError.invalid("A file changed while it was read.") }
        return data
    }
    private func directory(_ url: URL) throws {
        let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else {
            throw CharacterImportError.invalid("Choose a real Voices folder, rather than a shortcut.")
        }
    }
    private static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private static func waveSeconds(_ data: Data) throws -> Double {
        func fail() -> CharacterImportError { .invalid("The reference must contain audible mono 24 kHz WAV audio.") }
        let b = [UInt8](data)
        func number(_ p: Int, _ n: Int) -> Int {
            (0..<n).reduce(0) { $0 | Int(b[p + $1]) << (8 * $1) }
        }
        func tag(_ p: Int) -> String { String(bytes: b[p..<p+4], encoding: .ascii) ?? "" }
        guard b.count >= 44, tag(0) == "RIFF", tag(8) == "WAVE", number(4,4) == b.count - 8 else { throw fail() }
        var p = 12, pcm: Range<Int>?, formatOK = false
        while p + 8 <= b.count {
            let size = number(p+4,4), start = p+8
            guard size <= b.count - start else { throw fail() }
            if tag(p) == "fmt " {
                guard size >= 16, !formatOK, number(start,2) == 1, number(start+2,2) == 1,
                      number(start+4,4) == 24000, number(start+8,4) == 48000,
                      number(start+12,2) == 2, number(start+14,2) == 16 else { throw fail() }
                formatOK = true
            }
            if tag(p) == "data" {
                guard pcm == nil else { throw fail() }; pcm = start..<start+size
            }
            p = start + size + (size % 2)
        }
        guard p == b.count, formatOK, let pcm, pcm.count % 2 == 0,
              (24000...720000).contains(pcm.count) else { throw fail() }
        var energy = 0.0
        for offset in stride(from: pcm.lowerBound, to: pcm.upperBound, by: 2) {
            let sample = Double(Int16(bitPattern: UInt16(number(offset,2))))
            energy += sample * sample
        }
        guard energy / Double(pcm.count / 2) >= 16 else { throw fail() }
        return Double(pcm.count) / 48000
    }
    private func validated(_ folder: URL) throws -> (CharacterReference, Data, Data) {
        try directory(folder)
        let manifest = try regular(folder.appendingPathComponent("manifest.json"), limit: 65536)
        let voice = try JSONDecoder().decode(CharacterReference.self, from: manifest)
        guard Self.safeID(voice.id), voice.schemaVersion == 1, voice.kind == "f5-reference",
              voice.engine == "F5TTS_v1_Base", !voice.trainedModel, voice.referenceFile == "reference.wav",
              [voice.name, voice.source, voice.permission, voice.referenceText].allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              !voice.categories.isEmpty, voice.categories.count <= 50,
              voice.categories.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              Set(voice.categories).count == voice.categories.count else {
            throw CharacterImportError.invalid("The voice format or source information is incomplete.")
        }
        let audio = try regular(folder.appendingPathComponent("reference.wav"), limit: 848000)
        guard audio.count == voice.referenceBytes, Self.digest(audio) == voice.referenceSHA256,
              abs(try Self.waveSeconds(audio) - voice.seconds) < 0.000001 else {
            throw CharacterImportError.invalid("The reference audio is damaged or changed.")
        }
        return (voice, manifest, audio)
    }
    private func index() throws -> [String: String] {
        let file = root.appendingPathComponent("index.json")
        guard fm.fileExists(atPath: file.path) else { return [:] }
        let value = try JSONDecoder().decode([String: String].self, from: regular(file, limit: 512000))
        guard value.allSatisfy({ Self.safeID($0.key) && $0.value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }) else {
            throw CharacterImportError.invalid("The private library index needs repair.")
        }
        return value
    }
    func profiles() throws -> [CharacterReference] {
        try index().map { id, revision in
            let (voice, manifest, audio) = try validated(root.appendingPathComponent(revision))
            guard voice.id == id, Self.digest(manifest + audio) == revision else { throw CharacterImportError.invalid("A saved voice changed.") }
            return voice
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
    func referenceURL(id: String) throws -> URL {
        guard let revision = try index()[id] else { throw CharacterImportError.invalid("Choose an imported voice first.") }
        let folder = root.appendingPathComponent(revision)
        let (voice, manifest, audio) = try validated(folder)
        guard voice.id == id, Self.digest(manifest + audio) == revision else { throw CharacterImportError.invalid("The selected voice changed.") }
        return folder.appendingPathComponent("reference.wav")
    }
    func importCollection(at external: URL) throws -> [CharacterReference] {
        try directory(external)
        let collection = try JSONDecoder().decode(Collection.self, from: regular(external.appendingPathComponent("collection.json"), limit: 256000))
        guard collection.schemaVersion == 1, (1...1000).contains(collection.voices.count),
              Set(collection.voices.map(\.id)).count == collection.voices.count,
              Set(collection.voices.map(\.folder)).count == collection.voices.count,
              collection.voices.allSatisfy({ Self.safeID($0.id) && $0.folder == $0.id }) else {
            throw CharacterImportError.invalid("The collection contains duplicate or unsupported entries.")
        }
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        var next = try index()
        var referenceOwners: [String: String] = [:]
        let savedProfiles = try profiles()
        let savedByID = Dictionary(uniqueKeysWithValues: savedProfiles.map { ($0.id, $0) })
        for voice in savedProfiles {
            guard referenceOwners[voice.referenceSHA256] == nil else { throw CharacterImportError.invalid("The library contains repeated reference audio.") }
            referenceOwners[voice.referenceSHA256] = voice.id
        }
        for entry in collection.voices {
            try Task.checkCancellation()
            let (voice, manifest, audio) = try validated(external.appendingPathComponent(entry.folder))
            guard voice.id == entry.id else { throw CharacterImportError.invalid("The collection and voice IDs do not match.") }
            if let saved = savedByID[voice.id],
               saved.referenceSHA256 != voice.referenceSHA256 || saved.referenceText != voice.referenceText {
                throw CharacterImportError.invalid("A changed reference or transcript for " + saved.name + " needs a reviewed replacement. Your existing voices were kept.")
            }
            if let owner = referenceOwners[voice.referenceSHA256], owner != voice.id {
                throw CharacterImportError.invalid("This reference is already stored under another voice name.")
            }
            referenceOwners[voice.referenceSHA256] = voice.id
            let revision = Self.digest(manifest + audio)
            let destination = root.appendingPathComponent(revision)
            if !fm.fileExists(atPath: destination.path) {
                let stage = root.appendingPathComponent("stage-" + UUID().uuidString)
                defer { try? fm.removeItem(at: stage) }
                try fm.createDirectory(at: stage, withIntermediateDirectories: false)
                try manifest.write(to: stage.appendingPathComponent("manifest.json"))
                try audio.write(to: stage.appendingPathComponent("reference.wav"))
                _ = try validated(stage)
                try fm.moveItem(at: stage, to: destination)
            } else { _ = try validated(destination) }
            next[voice.id] = revision
        }
        try Task.checkCancellation()
        try JSONEncoder().encode(next).write(to: root.appendingPathComponent("index.json"), options: .atomic)
        return try profiles()
    }
}
