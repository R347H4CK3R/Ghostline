import Foundation

@main struct F5SpeechChunkChecks {
    static func main() throws {
        let reference = "This is a clear voice reference recording."
        let short = "I found a strange device near the portal."
        let one = try F5SpeechChunks.plan(text: short, referenceText: reference, referenceSeconds: 10)
        precondition(one == [short])
        let paragraph = Array(repeating: "Please bring the notebook and close the window.", count: 15).joined(separator: " ")
        let chunks = try F5SpeechChunks.plan(text: paragraph, referenceText: reference, referenceSeconds: 10)
        precondition(chunks.count > 1)
        precondition(chunks.joined(separator: " ").split(whereSeparator: \.isWhitespace) == paragraph.split(whereSeparator: \.isWhitespace), "No words may disappear or be reordered")
        for chunk in chunks {
            precondition(F5SpeechChunks.estimatedSeconds(text: chunk, referenceText: reference, referenceSeconds: 10) <= 22.01)
        }
        do {
            _ = try F5SpeechChunks.plan(text: String(repeating: "a", count: 300), referenceText: reference, referenceSeconds: 10)
            fatalError("An oversized unbroken word must not allocate an unbounded inference")
        } catch is F5ChunkError { }
        do {
            _ = try F5SpeechChunks.plan(text: "Hello", referenceText: String(repeating: "x", count: 2000), referenceSeconds: 10)
            fatalError("An implausible reference transcript must not allocate an unbounded token sequence")
        } catch is F5ChunkError { }
        try F5SpeechChunks.validateTokenCount(2061)
        do {
            try F5SpeechChunks.validateTokenCount(2062)
            fatalError("Tokenizer expansion must not bypass the frame budget")
        } catch is F5ChunkError { }
        let longText = Array(repeating: "Please bring the notebook and close the window.", count: 150).joined(separator: " ")
        precondition(longText.utf8.count > 5000)
        let longChunks = try F5SpeechChunks.plan(text: longText, referenceText: reference, referenceSeconds: 10)
        precondition(longChunks.joined(separator: " ").split(whereSeparator: \.isWhitespace) == longText.split(whereSeparator: \.isWhitespace))
        do {
            _ = try F5SpeechChunks.plan(text: Array(repeating: paragraph, count: 100).joined(separator: " "), referenceText: reference, referenceSeconds: 10)
            fatalError("Oversized duration job was not rejected")
        } catch F5ChunkError.jobTooLong { }
        print("F5 word preservation and bounded per-chunk inference planning passed")
    }
}
