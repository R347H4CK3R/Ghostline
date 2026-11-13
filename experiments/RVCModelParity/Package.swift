// swift-tools-version: 5.9
import PackageDescription
let package = Package(name:"RVCModelParity", platforms:[.macOS(.v14)], targets:[
 .binaryTarget(name:"onnxruntime",url:"https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.24.2.zip",checksum:"f7100a992d2a8135168c8afd831e6a58b465349101982aa58b3e11d36e600b54"),
 .executableTarget(name:"RVCModelParity",dependencies:["onnxruntime"],path:"Runner",linkerSettings:[.linkedFramework("Foundation"),.linkedFramework("CoreML")])
],cxxLanguageStandard:.cxx17)
