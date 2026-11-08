import Foundation

@main struct StudioActivityChecks {
    static func main() {
        var activity = StudioActivity()
        let speech = activity.claim(.processing)!
        precondition(activity.processingInUse && !activity.microphoneInUse)
        precondition(activity.claim(.processing) == nil && activity.claim(.microphone) == nil)
        activity.release(UUID())
        precondition(activity.processingInUse)
        activity.release(speech)
        let microphone = activity.claim(.microphone)!
        precondition(activity.microphoneInUse && !activity.processingInUse)
        precondition(activity.claim(.processing) == nil && activity.claim(.microphone) == nil)
        activity.release(speech)
        precondition(activity.microphoneInUse)
        activity.release(microphone)
        precondition(activity.claim(.processing) != nil)
        print("Shared microphone/processing ownership checks passed")
    }
}
