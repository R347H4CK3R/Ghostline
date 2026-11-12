import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
@main struct Checks {
 static func main() throws {
  let root=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false)
  defer { try? FileManager.default.removeItem(at:root) }
  func entry(_ n:Int) -> LocalStudioJournal.Event { .init(id:UUID(),time:Date(timeIntervalSince1970:Double(n)),stage:"Stage",message:"Event \(n)") }
  for n in 0..<180 { try LocalStudioJournal.append(entry(n),folder:root) }
  let first=try LocalStudioJournal.read(folder:root)
  precondition(first.events.first?.message=="Event 0" && first.total==180 && first.next==100)
  let next=try LocalStudioJournal.read(folder:root,offset:100)
  precondition(next.events.count==80 && next.next==nil && next.events.last?.message=="Event 179")
  try LocalStudioJournal.append(entry(180),folder:root) // restart/reopen never truncates
  let reopened=try LocalStudioJournal.read(folder:root);precondition(reopened.total==181)
  let clean=LocalStudioJournal.clean("https://host.test/private?token=x file:///private/data C:\\private\\file Bearer hidden")
  precondition(!clean.contains("host.test") && !clean.contains("hidden") && !clean.contains("private"))
  precondition(LocalStudioJournal.clean("3/10 F5/ASR") == "3/10 F5/ASR")
  let quoted=LocalStudioJournal.clean("Path \"/Users/Jane Doe/private.wav\" and \"C:\\Jane Doe\\secret.wav\"")
  precondition(!quoted.contains("Doe") && !quoted.contains("private.wav") && !quoted.contains("secret.wav"))
  let assignments=LocalStudioJournal.clean("token=abc API_KEY=xyz password:123 Bearer hidden")
  precondition(!assignments.contains("abc") && !assignments.contains("xyz") && !assignments.contains("123") && !assignments.contains("hidden"))
  let file=root.appendingPathComponent(LocalStudioJournal.filename)
  let h=try FileHandle(forWritingTo:file);try h.seekToEnd();try h.write(contentsOf:Data("broken".utf8));try h.close()
  let before=try Data(contentsOf:file)
  do { try LocalStudioJournal.append(entry(999),folder:root);preconditionFailure("Torn journal accepted") } catch { }
  let after=try Data(contentsOf:file);precondition(after==before)
  let other=root.appendingPathComponent("other");try FileManager.default.createDirectory(at:other,withIntermediateDirectories:false)
  try FileManager.default.createSymbolicLink(at:other.appendingPathComponent(LocalStudioJournal.filename),withDestinationURL:file)
  do { _=try LocalStudioJournal.read(folder:other);preconditionFailure("Link accepted") } catch { }
  let job=other.appendingPathComponent("job");try FileManager.default.createDirectory(at:job,withIntermediateDirectories:false)
  let alias=root.appendingPathComponent("parentAlias");try FileManager.default.createSymbolicLink(at:alias,withDestinationURL:other)
  do { _=try LocalStudioJournal.read(folder:alias);preconditionFailure("Linked job directory accepted") } catch { }
  do { try LocalStudioJournal.append(entry(1),folder:alias.appendingPathComponent("job"));preconditionFailure("Linked parent accepted") } catch { }
  let old=root.appendingPathComponent("old");try FileManager.default.createDirectory(at:old,withIntermediateDirectories:false)
  try LocalStudioJournal.append(entry(3),folder:old,legacy:[entry(1),entry(2)])
  let recovered=try LocalStudioJournal.read(folder:old);precondition(recovered.total==4)
  // The Python caller bounds this entire executable to 30s. Without NONBLOCK,
  // opening this reader-only FIFO would hang before any regular-file check.
  let fifoRoot=root.appendingPathComponent("fifo");try FileManager.default.createDirectory(at:fifoRoot,withIntermediateDirectories:false)
  let fifo=fifoRoot.appendingPathComponent(LocalStudioJournal.filename)
  precondition(mkfifo(fifo.path,mode_t(0o600))==0)
  do { _=try LocalStudioJournal.read(folder:fifoRoot);preconditionFailure("FIFO read accepted") } catch { }
  do { try LocalStudioJournal.append(entry(1),folder:fifoRoot);preconditionFailure("FIFO append accepted") } catch { }
  var fifoInfo=stat();precondition(lstat(fifo.path,&fifoInfo)==0 && fifoInfo.st_mode & mode_t(S_IFMT)==mode_t(S_IFIFO))
  let large=root.appendingPathComponent("large");try FileManager.default.createDirectory(at:large,withIntermediateDirectories:false)
  let largeFile=large.appendingPathComponent(LocalStudioJournal.filename)
  precondition(FileManager.default.createFile(atPath:largeFile.path,contents:nil))
  let big=try FileHandle(forWritingTo:largeFile);try big.truncate(atOffset:UInt64(LocalStudioJournal.maximumBytes+1));try big.close()
  do { try LocalStudioJournal.append(entry(4),folder:large);preconditionFailure("Oversized journal accepted") } catch { }
  let unchanged=try largeFile.resourceValues(forKeys:[.fileSizeKey]);precondition(unchanged.fileSize==LocalStudioJournal.maximumBytes+1)
  print("Foundation journal retention, pagination, redaction, legacy and damage/link guards passed")
 }
}
