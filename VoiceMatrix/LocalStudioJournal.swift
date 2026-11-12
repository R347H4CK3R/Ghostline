import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Private append-only JSONL. Bounded writes fail closed; never rotate/delete source history.
/// Callers serialize writes (the studio is MainActor-owned). No provider metadata is stored.
enum LocalStudioJournal {
    struct Event: Codable, Identifiable { let id: UUID; let time: Date; let stage: String; let message: String }
    struct Page {
        let events: [Event]
        let offset: Int
        let total: Int
        var next: Int? { offset + events.count < total ? offset + events.count : nil }
        var text: String { events.map { "\($0.time.ISO8601Format()) · \($0.stage)\n\($0.message)" }.joined(separator: "\n\n") }
    }
    enum Failure: LocalizedError {
        case unsafe, full, damaged
        var errorDescription: String? {
            switch self {
            case .unsafe: return "The private event journal could not be opened safely. Existing files were kept."
            case .full: return "The private event journal reached its 16 MB limit. Existing history was kept; start a new job."
            case .damaged: return "The event journal contains an incomplete or damaged entry. It was preserved without overwriting it."
            }
        }
    }
    static let maximumBytes = 16 * 1_024 * 1_024
    static let maximumEntryBytes = 8_192
    static let filename = "events-v1.jsonl"
    static func clean(_ text: String) -> String {
        // Defense in depth: callers supply status text only, never raw source/transcript data.
        var value=String(text.prefix(2_000))
        for pattern in ["(?i)[\"'](?:file://|/|[A-Z]:[\\\\/])[^\"'\\r\\n]*[\"']", "(?i)\\b(?:https?|file)://[^\\s]+", "(?i)\\b(?:bearer\\s+|(?:token|password|secret|api[_-]?key)\\s*(?:[:=]\\s*|\\s+))[^\\s]+", "(?<![^\\s\"'])(?:[A-Za-z]:[\\\\/]|/)[^\\s]+"] {
            value=value.replacingOccurrences(of:pattern,with:"[redacted]",options:.regularExpression)
        }
        return value.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) || $0 == "\n" || $0 == "\t" }.map(String.init).joined()
    }
    static func sanitized(_ event: Event) -> Event {
        Event(id:event.id,time:event.time,stage:clean(event.stage),message:clean(event.message))
    }
    private static func openJournal(folder: URL, writing: Bool) throws -> FileHandle {
        guard folder.isFileURL else { throw Failure.unsafe }
        let component=folder.lastPathComponent
        guard !component.isEmpty,component != ".",component != "..",!component.contains("/") else { throw Failure.unsafe }
        // Higher OS/app-container ancestors are trusted. Anchor the immediate parent,
        // then resolve only one job component and one fixed filename without links.
        // Descriptor-relative opens prevent a later parent/job path swap redirecting IO.
        let directoryFlags=O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC
        let parentFD=open(folder.deletingLastPathComponent().path,directoryFlags)
        guard parentFD>=0 else { throw Failure.unsafe }
        defer { close(parentFD) }
        let folderFD=openat(parentFD,component,directoryFlags)
        guard folderFD>=0 else { throw Failure.unsafe }
        defer { close(folderFD) }
        // NONBLOCK prevents a pre-existing FIFO/device from hanging before fstat.
        let flags=(writing ? O_RDWR | O_APPEND | O_CREAT : O_RDONLY) | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC
        let fd=openat(folderFD,filename,flags,mode_t(0o600))
        guard fd>=0 else { throw Failure.unsafe }
        var info=stat()
        guard fstat(fd,&info)==0,info.st_mode & mode_t(S_IFMT)==mode_t(S_IFREG),info.st_nlink==1 else { close(fd);throw Failure.unsafe }
        guard info.st_size>=0,Int64(info.st_size)<=Int64(maximumBytes) else { close(fd);throw Failure.full }
        return FileHandle(fileDescriptor:fd,closeOnDealloc:true)
    }
    static func append(_ event: Event, folder: URL, legacy: [Event] = []) throws {
        let handle=try openJournal(folder:folder,writing:true);defer { try? handle.close() }
        let size=try handle.seekToEnd()
        if size>0 {
            try handle.seek(toOffset:size-1)
            guard try handle.read(upToCount:1)==Data([10]) else { throw Failure.damaged }
        }
        var events:[Event]=[]
        if size==0, !legacy.isEmpty {
            events.append(Event(id:UUID(),time:Date(),stage:"Earlier snapshot recovered",message:"This older job predates durable logging. Only its retained snapshot is available; previously truncated events cannot be recovered."))
            events.append(contentsOf:legacy.prefix(160))
        }
        events.append(event)
        var bytes=Data()
        for item in events {
            let line=try JSONEncoder().encode(sanitized(item))
            guard line.count<=maximumEntryBytes else { throw Failure.full }
            bytes.append(line);bytes.append(10)
        }
        guard size+UInt64(bytes.count)<=maximumBytes else { throw Failure.full }
        try handle.write(contentsOf:bytes)
        try handle.synchronize()
    }
    static func read(folder: URL, offset: Int = 0, limit: Int = 100) throws -> Page {
        guard offset>=0,(1...100).contains(limit) else { throw Failure.unsafe }
        let handle=try openJournal(folder:folder,writing:false);defer { try? handle.close() }
        let data=try handle.read(upToCount:maximumBytes+1) ?? Data()
        guard data.count<=maximumBytes else { throw Failure.full }
        guard data.isEmpty || data.last==10 else { throw Failure.damaged }
        var selected:[Event]=[],total=0
        for line in data.split(separator:10,omittingEmptySubsequences:false).dropLast() {
            guard !line.isEmpty,line.count<=maximumEntryBytes else { throw Failure.damaged }
            let event:Event
            do { event=try JSONDecoder().decode(Event.self,from:Data(line)) } catch { throw Failure.damaged }
            guard event.time.timeIntervalSince1970.isFinite else { throw Failure.damaged }
            if total>=offset,selected.count<limit { selected.append(sanitized(event)) }
            total += 1
        }
        return Page(events:selected,offset:offset,total:total)
    }
}
