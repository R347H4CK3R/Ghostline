import Foundation
@main struct BundledASRPolicyChecks {
    static func main() {
        precondition(BundledASRPolicy.admittedTokenMean([]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([.nan]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([.infinity]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([-0.1]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([1.1]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([0.34]) == nil)
        precondition(BundledASRPolicy.admittedTokenMean([0.35]) == 0.35)
        precondition(BundledASRPolicy.admittedTokenMean([0.4,0.8])! > 0.59)
        precondition(BundledASRPolicy.admittedTokenMean(Array(repeating:1,count:4097)) == nil)
        print("Bundled ASR policy checks passed")
    }
}
