import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("usage: ocr_body.swift IMAGE\n".utf8))
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL
guard let source = CGImageSourceCreateWithURL(imageURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    FileHandle.standardError.write(Data("could not read image\n".utf8))
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["ar-EG", "ar", "en-US"]
let handler = VNImageRequestHandler(cgImage: image, orientation: .up)
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write(Data("Vision OCR failed: \(error)\n".utf8))
    exit(4)
}

let observations = (request.results ?? []).sorted { left, right in
    if abs(left.boundingBox.midY - right.boundingBox.midY) > 0.03 {
        return left.boundingBox.midY > right.boundingBox.midY
    }
    return left.boundingBox.midX > right.boundingBox.midX
}

var lines: [String] = []
var glyphs: [[String: Any]] = []
for observation in observations {
    guard let candidate = observation.topCandidates(1).first else { continue }
    lines.append(candidate.string)
    let string = candidate.string
    for index in string.indices {
        let next = string.index(after: index)
        let character = String(string[index..<next])
        guard character == "«" || character == "»" else { continue }
        if let box = try? candidate.boundingBox(for: index..<next) {
            let rect = box.boundingBox
            glyphs.append([
                "char": character,
                "x": rect.origin.x,
                "y": 1.0 - rect.origin.y - rect.height,
                "w": rect.width,
                "h": rect.height,
            ])
        }
    }
}

let payload: [String: Any] = ["text": lines.joined(separator: "\n"), "lines": lines, "glyphs": glyphs]
let json = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(json)
FileHandle.standardOutput.write(Data("\n".utf8))
