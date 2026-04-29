#!/usr/bin/swift

import AppKit
import Foundation
import Vision

struct ReviewPayload {
    let result: String
    let image: String
    let provider: String
    let ocrText: String
    let layoutPass: Bool
    let acronymBreakPass: Bool
    let visualQualityScore: Double
    let aiArtifactScore: Double
    let brandFitScore: Double
    let status: String
    let decision: String
    let blockingFindings: [String]
}

struct ImageMetrics {
    let meanLuma: Double
    let meanSaturation: Double
    let brightFraction: Double
    let darkFraction: Double
}

func cliArgs() -> [String: String] {
    var values: [String: String] = [:]
    var index = 1
    while index < CommandLine.arguments.count {
        let key = CommandLine.arguments[index]
        if key.hasPrefix("--"), index + 1 < CommandLine.arguments.count {
            values[key] = CommandLine.arguments[index + 1]
            index += 2
        } else {
            index += 1
        }
    }
    return values
}

func expandPath(_ value: String) -> String {
    NSString(string: value).expandingTildeInPath
}

func loadJSON(_ path: String?) -> [String: Any] {
    guard let path, !path.isEmpty else { return [:] }
    let resolved = expandPath(path)
    guard FileManager.default.fileExists(atPath: resolved) else { return [:] }
    do {
        let data = try Data(contentsOf: URL(fileURLWithPath: resolved))
        let raw = try JSONSerialization.jsonObject(with: data)
        return raw as? [String: Any] ?? [:]
    } catch {
        return [:]
    }
}

func normalizeText(_ value: String) -> String {
    value
        .replacingOccurrences(of: "\u{3000}", with: " ")
        .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

func compactText(_ value: String) -> String {
    normalizeText(value)
        .replacingOccurrences(of: "[^A-Za-z0-9\\u4e00-\\u9fff]+", with: "", options: .regularExpression)
        .lowercased()
}

func expectedTexts(copy: [String: Any], titlePack: [String: Any]) -> [String] {
    let values = [
        titlePack["cover_headline"] as? String,
        titlePack["cover_subhead"] as? String,
        copy["marketing_headline"] as? String,
        copy["subhead"] as? String,
        copy["supporting_headline"] as? String,
    ]
    return values.compactMap { raw in
        let cleaned = normalizeText(raw ?? "")
        return cleaned.isEmpty ? nil : cleaned
    }
}

func expectedAcronyms(from texts: [String]) -> [String] {
    let pattern = try! NSRegularExpression(pattern: "\\b[A-Z]{2,}\\b")
    var tokens: [String] = []
    for text in texts {
        let nsText = text as NSString
        let matches = pattern.matches(in: text, range: NSRange(location: 0, length: nsText.length))
        for match in matches {
            let token = nsText.substring(with: match.range)
            if !tokens.contains(token) {
                tokens.append(token)
            }
        }
    }
    return tokens
}

func makeCGImage(_ image: NSImage) -> CGImage? {
    var rect = NSRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)
}

func recognizeText(_ cgImage: CGImage) -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return []
    }
    let observations = (request.results ?? []).sorted {
        if abs($0.boundingBox.minY - $1.boundingBox.minY) > 0.02 {
            return $0.boundingBox.minY > $1.boundingBox.minY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    return observations.compactMap { observation in
        observation.topCandidates(1).first?.string
    }.map(normalizeText).filter { !$0.isEmpty }
}

func analyzeImage(_ cgImage: CGImage) -> ImageMetrics {
    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    let width = max(bitmap.pixelsWide, 1)
    let height = max(bitmap.pixelsHigh, 1)
    let step = max(min(width, height) / 160, 6)

    var sampleCount = 0.0
    var lumaSum = 0.0
    var saturationSum = 0.0
    var brightCount = 0.0
    var darkCount = 0.0

    var y = 0
    while y < height {
        var x = 0
        while x < width {
            guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
                x += step
                continue
            }
            let r = Double(color.redComponent)
            let g = Double(color.greenComponent)
            let b = Double(color.blueComponent)
            let maxValue = max(r, max(g, b))
            let minValue = min(r, min(g, b))
            let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            let saturation = maxValue - minValue
            sampleCount += 1
            lumaSum += luma
            saturationSum += saturation
            if luma > 0.92 { brightCount += 1 }
            if luma < 0.08 { darkCount += 1 }
            x += step
        }
        y += step
    }

    let safeCount = max(sampleCount, 1.0)
    return ImageMetrics(
        meanLuma: lumaSum / safeCount,
        meanSaturation: saturationSum / safeCount,
        brightFraction: brightCount / safeCount,
        darkFraction: darkCount / safeCount
    )
}

func scoreVisualQuality(_ metrics: ImageMetrics) -> Double {
    var score = 0.86
    score -= min(abs(metrics.meanLuma - 0.40) * 0.8, 0.28)
    score -= min(abs(metrics.meanSaturation - 0.20) * 0.7, 0.20)
    score -= metrics.brightFraction * 0.35
    score -= metrics.darkFraction * 0.16
    return max(0.0, min(1.0, score))
}

func brandFitScore(_ metrics: ImageMetrics, provider: String) -> Double {
    var score = 0.70
    if metrics.meanSaturation > 0.12 && metrics.meanSaturation < 0.42 {
        score += 0.10
    }
    if provider == "deterministic_cover" || provider == "local_collage" {
        score += 0.08
    }
    return max(0.0, min(1.0, score))
}

func aiArtifactScore(provider: String) -> Double {
    if provider == "deterministic_cover" || provider == "local_collage" {
        return 0.12
    }
    if provider == "fallback_collage" {
        return 0.18
    }
    return 0.48
}

func containsExpectedText(ocrLines: [String], expected: [String]) -> Bool {
    guard !expected.isEmpty else { return true }
    let compactOCR = compactText(ocrLines.joined(separator: " "))
    for value in expected {
        if compactOCR.contains(compactText(value)) {
            return true
        }
    }
    return false
}

func acronymBreakPass(ocrLines: [String], acronyms: [String]) -> Bool {
    guard !acronyms.isEmpty else { return true }
    let ocrText = ocrLines.joined(separator: "\n")
    let compactOCR = compactText(ocrText)
    for token in acronyms {
        if compactOCR.contains(token.lowercased()) {
            continue
        }
        let spacedPattern = token.map { String($0) }.joined(separator: "\\s+")
        if ocrText.range(of: spacedPattern, options: .regularExpression) != nil {
            return false
        }
    }
    return true
}

func writeJSON(_ payload: [String: Any], to path: String?) {
    guard let path, !path.isEmpty else { return }
    let resolved = expandPath(path)
    let url = URL(fileURLWithPath: resolved)
    try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) else { return }
    try? data.write(to: url)
}

let args = cliArgs()
guard let imageArg = args["--image"] else {
    fputs("missing --image\n", stderr)
    exit(2)
}

let imagePath = expandPath(imageArg)
guard let image = NSImage(contentsOfFile: imagePath), let cgImage = makeCGImage(image) else {
    fputs("could not load image \(imagePath)\n", stderr)
    exit(2)
}

let copyPayload = loadJSON(args["--copy-json"])
let titlePack = loadJSON(args["--title-pack"])
let provider = normalizeText(args["--provider"] ?? "deterministic_cover")
let ocrLines = recognizeText(cgImage)
let expected = expectedTexts(copy: copyPayload, titlePack: titlePack)
let acronyms = expectedAcronyms(from: expected)
let metrics = analyzeImage(cgImage)
let layoutPass = containsExpectedText(ocrLines: ocrLines, expected: expected)
let acronymPass = acronymBreakPass(ocrLines: ocrLines, acronyms: acronyms)
let visualScore = scoreVisualQuality(metrics)
let artifactScore = aiArtifactScore(provider: provider)
let fitScore = brandFitScore(metrics, provider: provider)

var blocking: [String] = []
if !layoutPass {
    blocking.append("cover_ocr_missing_expected_headline")
}
if !acronymPass {
    blocking.append("cover_acronym_broken")
}
if visualScore < 0.42 {
    blocking.append("cover_visual_quality_too_low")
}

let status = blocking.isEmpty ? "pass" : "fail"
let decision = status == "pass" ? "use_cover" : "regenerate_cover"
let payload: [String: Any] = [
    "result": "success",
    "image": imagePath,
    "provider": provider,
    "ocr_text": ocrLines.joined(separator: "\n"),
    "expected_texts": expected,
    "layout_pass": layoutPass,
    "acronym_break_pass": acronymPass,
    "visual_quality_score": visualScore,
    "ai_artifact_score": artifactScore,
    "brand_fit_score": fitScore,
    "status": status,
    "decision": decision,
    "blocking_findings": blocking,
]

writeJSON(payload, to: args["--out"])
if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]),
   let text = String(data: data, encoding: .utf8) {
    print(text)
}
