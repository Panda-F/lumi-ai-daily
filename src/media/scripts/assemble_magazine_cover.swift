#!/usr/bin/env swift

import AppKit
import CoreImage
import Foundation
import Vision

struct Asset: Decodable {
    let file: String
}

struct Manifest: Decodable {
    let assets: [Asset]
}

struct CopySpec: Decodable {
    let masthead: String?
    let kicker: String?
    let marketingHeadline: String?
    let headline: String?
    let subhead: String?
    let supportingHeadline: String?
    let leftLines: [String]?
    let rightLines: [String]?
    let trendWords: [String]?

    enum CodingKeys: String, CodingKey {
        case masthead
        case kicker
        case marketingHeadline = "marketing_headline"
        case headline
        case subhead
        case supportingHeadline = "supporting_headline"
        case leftLines = "left_lines"
        case rightLines = "right_lines"
        case trendWords = "trend_words"
    }
}

struct CoverText {
    let masthead: String
    let kicker: String
    let marketingHeadline: String
    let subhead: String
    let leftLine: String?
    let rightLine: String?
}

struct ImageMetrics {
    let aspectRatio: CGFloat
    let meanLuma: CGFloat
    let brightFraction: CGFloat
    let darkFraction: CGFloat
    let saturationMean: CGFloat
    let textCount: Int
    let textCoverage: CGFloat
}

struct AssetCandidate {
    let url: URL
    let image: NSImage
    let cgImage: CGImage
    let metrics: ImageMetrics
    let rejected: Bool
    let reasons: [String]
    let score: CGFloat
}

struct SelectedAssets {
    let background: AssetCandidate?
    let sticker: AssetCandidate?
    let accepted: [AssetCandidate]
    let rejected: [AssetCandidate]
}

let canvasWidth: CGFloat = 1920
let canvasHeight: CGFloat = 1080
let defaultLumiPath = "/Users/dystopia/.openclaw/workspace/assets/lumi-cover-ref.png"

func parseArguments() -> [String: String] {
    var result: [String: String] = [:]
    var index = 1
    while index < CommandLine.arguments.count {
        let key = CommandLine.arguments[index]
        if key.hasPrefix("--"), index + 1 < CommandLine.arguments.count {
            result[key] = CommandLine.arguments[index + 1]
            index += 2
        } else {
            index += 1
        }
    }
    return result
}

func expandPath(_ raw: String) -> String {
    NSString(string: raw).expandingTildeInPath
}

func splitLines(_ raw: String?) -> [String] {
    guard let raw, !raw.isEmpty else { return [] }
    return raw
        .split(separator: "|")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
}

func isStyleReference(_ path: String) -> Bool {
    let lowered = path.lowercased()
    return lowered.contains("/style-references/") || lowered.contains("tech-daily-short-video-reference")
}

func makeCGImage(_ image: NSImage) -> CGImage? {
    var proposedRect = NSRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil)
}

func detectTextMetrics(_ cgImage: CGImage) -> (Int, CGFloat) {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.02
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return (0, 0)
    }
    let observations = request.results ?? []
    let coverage = observations.reduce(CGFloat(0)) { partial, observation in
        partial + observation.boundingBox.width * observation.boundingBox.height
    }
    return (observations.count, coverage)
}

func analyzeImage(_ cgImage: CGImage) -> ImageMetrics {
    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    let width = max(bitmap.pixelsWide, 1)
    let height = max(bitmap.pixelsHigh, 1)
    let step = max(min(width, height) / 140, 6)

    var sampleCount: CGFloat = 0
    var lumaSum: CGFloat = 0
    var saturationSum: CGFloat = 0
    var brightCount: CGFloat = 0
    var darkCount: CGFloat = 0

    var y = 0
    while y < height {
        var x = 0
        while x < width {
            guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
                x += step
                continue
            }
            let r = color.redComponent
            let g = color.greenComponent
            let b = color.blueComponent
            let maxValue = max(r, max(g, b))
            let minValue = min(r, min(g, b))
            let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            let saturation = maxValue - minValue

            sampleCount += 1
            lumaSum += luma
            saturationSum += saturation
            if luma > 0.9 { brightCount += 1 }
            if luma < 0.1 { darkCount += 1 }
            x += step
        }
        y += step
    }

    let safeCount = max(sampleCount, 1)
    let (textCount, textCoverage) = detectTextMetrics(cgImage)
    return ImageMetrics(
        aspectRatio: CGFloat(width) / CGFloat(height),
        meanLuma: lumaSum / safeCount,
        brightFraction: brightCount / safeCount,
        darkFraction: darkCount / safeCount,
        saturationMean: saturationSum / safeCount,
        textCount: textCount,
        textCoverage: textCoverage
    )
}

func filenameSignals(_ path: String) -> [String] {
    let lowered = path.lowercased()
    let patterns = [
        ("qr", "qr"),
        ("qrcode", "qr"),
        ("scan", "qr"),
        ("browser", "browser"),
        ("chatgpt", "browser"),
        ("xiaohongshu", "browser"),
        ("notebooklm", "browser"),
        ("login", "browser"),
        ("search", "browser"),
        ("exploit", "chart"),
        ("chart", "chart"),
        ("eval", "chart"),
        ("benchmark", "chart"),
        ("result", "chart"),
        ("results", "chart"),
        ("score", "chart"),
        ("matrix", "chart"),
        ("table", "chart"),
        ("arena", "chart")
    ]
    return patterns.compactMap { lowered.contains($0.0) ? $0.1 : nil }
}

func evaluateCandidate(url: URL, image: NSImage, cgImage: CGImage) -> AssetCandidate {
    let metrics = analyzeImage(cgImage)
    var reasons = filenameSignals(url.lastPathComponent)

    if metrics.brightFraction > 0.70 && metrics.meanLuma > 0.72 {
        reasons.append("too-bright")
    }
    if metrics.textCoverage > 0.18 ||
        (metrics.textCoverage > 0.06 && metrics.textCount >= 14) ||
        (metrics.textCount >= 20 && metrics.saturationMean < 0.18) {
        reasons.append("heavy-ui-text")
    }
    if metrics.textCoverage > 0.10 && metrics.meanLuma > 0.64 && metrics.saturationMean < 0.18 {
        reasons.append("chart-like")
    }
    if metrics.saturationMean < 0.05 && metrics.meanLuma > 0.68 {
        reasons.append("document-like")
    }

    let uniqueReasons = Array(Set(reasons)).sorted()
    var score: CGFloat = 0
    score += max(0, 1.6 - abs(metrics.aspectRatio - 1.78)) * 3
    score += max(0, 0.55 - abs(metrics.meanLuma - 0.38)) * 6
    score += max(0, metrics.saturationMean - 0.05) * 3
    score -= metrics.brightFraction * 3
    score -= metrics.textCoverage * 14
    score -= CGFloat(metrics.textCount) * 0.12
    score -= CGFloat(uniqueReasons.count) * 3.5

    return AssetCandidate(
        url: url,
        image: image,
        cgImage: cgImage,
        metrics: metrics,
        rejected: !uniqueReasons.isEmpty,
        reasons: uniqueReasons,
        score: score
    )
}

func loadCandidates(manifestPath: String) throws -> [AssetCandidate] {
    let data = try Data(contentsOf: URL(fileURLWithPath: expandPath(manifestPath)))
    let manifest = try JSONDecoder().decode(Manifest.self, from: data)

    var candidates: [AssetCandidate] = []
    for asset in manifest.assets {
        if isStyleReference(asset.file) {
            continue
        }
        let url = URL(fileURLWithPath: asset.file)
        guard FileManager.default.fileExists(atPath: url.path) else { continue }
        guard let image = NSImage(contentsOf: url), let cgImage = makeCGImage(image) else { continue }
        candidates.append(evaluateCandidate(url: url, image: image, cgImage: cgImage))
    }
    return candidates
}

func loadCopySpec(_ path: String?) -> CopySpec? {
    guard let path else { return nil }
    let resolved = expandPath(path)
    guard FileManager.default.fileExists(atPath: resolved) else { return nil }
    do {
        let data = try Data(contentsOf: URL(fileURLWithPath: resolved))
        return try JSONDecoder().decode(CopySpec.self, from: data)
    } catch {
        fputs("warning: failed to load copy json \(resolved): \(error)\n", stderr)
        return nil
    }
}

func selectAssets(_ candidates: [AssetCandidate]) -> SelectedAssets {
    let accepted = candidates.filter { !$0.rejected }.sorted { $0.score > $1.score }
    let rejected = candidates.filter(\.rejected).sorted { $0.score > $1.score }

    let background = accepted.first ?? candidates.sorted { $0.score > $1.score }.first
    let preferredSticker = accepted.first { candidate in
        guard let background else { return false }
        guard candidate.url.path != background.url.path else { return false }
        return candidate.metrics.textCoverage < 0.08 && candidate.metrics.brightFraction < 0.50
    }
    let fallbackAcceptedSticker = accepted.first { candidate in
        guard let background else { return false }
        return candidate.url.path != background.url.path
    }
    let fallbackRejectedSticker = rejected.first { candidate in
        guard let background else { return false }
        guard candidate.url.path != background.url.path else { return false }
        let allowedReasons = Set(["document-like", "too-bright"])
        return !candidate.reasons.isEmpty &&
            Set(candidate.reasons).isSubset(of: allowedReasons) &&
            candidate.metrics.textCoverage < 0.18
    }
    let sticker = preferredSticker ?? fallbackAcceptedSticker ?? fallbackRejectedSticker

    return SelectedAssets(background: background, sticker: sticker, accepted: accepted, rejected: rejected)
}

func fillRoundedRect(_ rect: NSRect, radius: CGFloat, color: NSColor) {
    color.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}

func strokeRoundedRect(_ rect: NSRect, radius: CGFloat, color: NSColor, lineWidth: CGFloat) {
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    path.lineWidth = lineWidth
    color.setStroke()
    path.stroke()
}

func clipToRoundedRect(_ rect: NSRect, radius: CGFloat, _ block: () -> Void) {
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).addClip()
    block()
    NSGraphicsContext.restoreGraphicsState()
}

func drawFillImage(
    _ image: NSImage,
    in rect: NSRect,
    horizontalAlignment: CGFloat = 0.5,
    verticalAlignment: CGFloat = 0.5,
    alpha: CGFloat = 1.0
) {
    let imageSize = image.size
    guard imageSize.width > 0, imageSize.height > 0 else { return }

    let destinationRatio = rect.width / rect.height
    let imageRatio = imageSize.width / imageSize.height

    var sourceRect = NSRect(origin: .zero, size: imageSize)
    if imageRatio > destinationRatio {
        let newWidth = imageSize.height * destinationRatio
        sourceRect.origin.x = (imageSize.width - newWidth) * max(0, min(horizontalAlignment, 1))
        sourceRect.size.width = newWidth
    } else {
        let newHeight = imageSize.width / destinationRatio
        sourceRect.origin.y = (imageSize.height - newHeight) * max(0, min(verticalAlignment, 1))
        sourceRect.size.height = newHeight
    }

    image.draw(in: rect, from: sourceRect, operation: .sourceOver, fraction: alpha)
}

func paragraphStyle(alignment: NSTextAlignment, lineHeight: CGFloat? = nil) -> NSMutableParagraphStyle {
    let style = NSMutableParagraphStyle()
    style.alignment = alignment
    style.lineBreakMode = .byWordWrapping
    if let lineHeight {
        style.minimumLineHeight = lineHeight
        style.maximumLineHeight = lineHeight
    }
    return style
}

func drawParagraph(
    _ text: String,
    rect: NSRect,
    font: NSFont,
    color: NSColor,
    alignment: NSTextAlignment = .left,
    lineHeight: CGFloat? = nil
) {
    let attributes: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: paragraphStyle(alignment: alignment, lineHeight: lineHeight)
    ]
    NSAttributedString(string: text, attributes: attributes).draw(with: rect)
}

func drawOutlinedText(
    _ text: String,
    rect: NSRect,
    font: NSFont,
    fillColor: NSColor,
    strokeColor: NSColor,
    strokeRadius: CGFloat,
    shadowColor: NSColor,
    shadowBlur: CGFloat,
    alignment: NSTextAlignment = .left
) {
    let baseAttributes: [NSAttributedString.Key: Any] = [
        .font: font,
        .paragraphStyle: paragraphStyle(alignment: alignment)
    ]

    let outline = NSAttributedString(
        string: text,
        attributes: baseAttributes.merging([.foregroundColor: strokeColor]) { _, new in new }
    )

    for radius in [strokeRadius, max(strokeRadius * 0.55, 3)] {
        for angle in stride(from: 0.0, to: 360.0, by: 30.0) {
            let radians = CGFloat(angle) * .pi / 180
            let offset = rect.offsetBy(dx: cos(radians) * radius, dy: sin(radians) * radius)
            outline.draw(with: offset)
        }
    }

    let shadow = NSShadow()
    shadow.shadowColor = shadowColor
    shadow.shadowBlurRadius = shadowBlur
    shadow.shadowOffset = CGSize(width: 0, height: -3)

    let fill = NSAttributedString(
        string: text,
        attributes: baseAttributes.merging([
            .foregroundColor: fillColor,
            .shadow: shadow
        ]) { _, new in new }
    )
    fill.draw(with: rect)
}

func drawGradient(_ rect: NSRect, colors: [NSColor], angle: CGFloat) {
    guard let gradient = NSGradient(colors: colors) else { return }
    gradient.draw(in: rect, angle: angle)
}

func blurredImage(from cgImage: CGImage, radius: Double) -> NSImage? {
    let ciContext = CIContext(options: nil)
    let input = CIImage(cgImage: cgImage)
    let clamp = input.clampedToExtent()
    guard let filter = CIFilter(name: "CIGaussianBlur") else {
        return nil
    }
    filter.setValue(clamp, forKey: kCIInputImageKey)
    filter.setValue(radius, forKey: kCIInputRadiusKey)
    guard let output = filter.outputImage?.cropped(to: input.extent),
          let result = ciContext.createCGImage(output, from: input.extent) else {
        return nil
    }
    return NSImage(cgImage: result, size: NSSize(width: cgImage.width, height: cgImage.height))
}

func drawNewsCard(text: CoverText) {
    let card = NSRect(x: 42, y: 848, width: 322, height: 176)
    NSGraphicsContext.current?.cgContext.saveGState()
    NSGraphicsContext.current?.cgContext.setShadow(offset: CGSize(width: 0, height: -6),
                                                   blur: 18,
                                                   color: NSColor.black.withAlphaComponent(0.22).cgColor)
    fillRoundedRect(card, radius: 20, color: NSColor.white.withAlphaComponent(0.92))
    NSGraphicsContext.current?.cgContext.restoreGState()
    strokeRoundedRect(card, radius: 20, color: NSColor(calibratedRed: 0.95, green: 0.49, blue: 0.72, alpha: 0.58), lineWidth: 2)

    drawParagraph("NEWS",
                  rect: NSRect(x: 68, y: 934, width: 180, height: 40),
                  font: NSFont.boldSystemFont(ofSize: 34),
                  color: NSColor(calibratedWhite: 0.28, alpha: 1.0))
    drawParagraph(text.masthead,
                  rect: NSRect(x: 70, y: 862, width: 180, height: 34),
                  font: NSFont.systemFont(ofSize: 28, weight: .heavy),
                  color: NSColor(calibratedRed: 0.84, green: 0.28, blue: 0.54, alpha: 1.0))
    drawParagraph(shortDate(text.kicker),
                  rect: NSRect(x: 70, y: 820, width: 220, height: 24),
                  font: NSFont.systemFont(ofSize: 18, weight: .semibold),
                  color: NSColor(calibratedRed: 0.50, green: 0.56, blue: 0.66, alpha: 0.95))

    fillRoundedRect(NSRect(x: 70, y: 902, width: 114, height: 8), radius: 4, color: NSColor(calibratedRed: 0.96, green: 0.52, blue: 0.72, alpha: 1.0))
    fillRoundedRect(NSRect(x: 70, y: 886, width: 144, height: 8), radius: 4, color: NSColor(calibratedRed: 0.51, green: 0.76, blue: 1.0, alpha: 1.0))
    fillRoundedRect(NSRect(x: 70, y: 804, width: 108, height: 7), radius: 3.5, color: NSColor(calibratedRed: 0.82, green: 0.87, blue: 0.94, alpha: 1.0))
    fillRoundedRect(NSRect(x: 70, y: 792, width: 156, height: 7), radius: 3.5, color: NSColor(calibratedRed: 0.70, green: 0.84, blue: 1.0, alpha: 1.0))

    let ringCenter = CGPoint(x: 262, y: 998)
    for (radius, color, width) in [
        (42.0, NSColor(calibratedRed: 0.98, green: 0.60, blue: 0.74, alpha: 1.0), 11.0),
        (31.0, NSColor(calibratedRed: 0.46, green: 0.68, blue: 1.0, alpha: 1.0), 10.0),
        (20.0, NSColor(calibratedWhite: 0.18, alpha: 1.0), 8.0)
    ] {
        let path = NSBezierPath()
        path.appendArc(withCenter: ringCenter, radius: radius, startAngle: 0, endAngle: 360)
        path.lineWidth = width
        color.setStroke()
        path.stroke()
    }
}

func splitHeadline(_ text: String) -> [String] {
    let compact = text.replacingOccurrences(of: " ", with: "")
    if compact.count <= 8 { return [compact] }
    let separators = ["进入", "开始", "走向", "转向", "重写", "吞掉", "改写", "外包", "升温", "落地", "把", "后", "抢", "比"]
    if compact.count <= 22 {
        for separator in separators {
            if let range = compact.range(of: separator) {
                let left = String(compact[..<range.lowerBound])
                let right = String(compact[range.lowerBound...])
                if (3...10).contains(left.count) && (3...12).contains(right.count) {
                    return [left, right]
                }
            }
        }
    }
    let punctuationPattern = "[，、；：,;:]"
    let phrases = compact
        .replacingOccurrences(of: punctuationPattern, with: "|", options: .regularExpression)
        .split(separator: "|")
        .map(String.init)
        .filter { !$0.isEmpty }
    let lineCount = min(4, max(1, Int(ceil(Double(compact.count) / 13.0))))
    let target = max(8, Int(ceil(Double(compact.count) / Double(lineCount))))
    let characters = Array(compact)
    func isAlphaNumeric(_ character: Character) -> Bool {
        String(character).range(of: #"[A-Za-z0-9]"#, options: .regularExpression) != nil
    }
    func splitChunk(_ chunk: String, targetLength: Int) -> [String] {
        let chunkCharacters = Array(chunk)
        if chunkCharacters.count <= targetLength + 3 { return [chunk] }
        var output: [String] = []
        var start = 0
        while start < chunkCharacters.count {
            var end = min(chunkCharacters.count, start + targetLength)
            if end < chunkCharacters.count,
               end > start,
               isAlphaNumeric(chunkCharacters[end - 1]),
               isAlphaNumeric(chunkCharacters[end]) {
                var left = end
                while left > start && isAlphaNumeric(chunkCharacters[left - 1]) { left -= 1 }
                if left > start {
                    end = left
                } else {
                    var right = end
                    while right < chunkCharacters.count && isAlphaNumeric(chunkCharacters[right]) { right += 1 }
                    end = min(right, chunkCharacters.count)
                }
            }
            output.append(String(chunkCharacters[start..<end]))
            start = end
        }
        return output
    }
    var lines: [String] = []
    for phrase in phrases.isEmpty ? [compact] : phrases {
        lines.append(contentsOf: splitChunk(phrase, targetLength: target))
    }
    while lines.count > 4 {
        let last = lines.removeLast()
        lines[lines.count - 1] += last
    }
    if lines.count > 1 { return lines }
    for separator in separators {
        if let range = compact.range(of: separator) {
            let left = String(compact[..<range.lowerBound])
            let right = String(compact[range.lowerBound...])
            if (3...8).contains(left.count) && (3...9).contains(right.count) {
                return [left, right]
            }
        }
    }
    let midpoint = compact.count / 2
    var split = midpoint
    if split > 0 && split < characters.count && isAlphaNumeric(characters[split - 1]) && isAlphaNumeric(characters[split]) {
        var left = split
        while left > 0 && isAlphaNumeric(characters[left - 1]) { left -= 1 }
        var right = split
        while right < characters.count && isAlphaNumeric(characters[right]) { right += 1 }
        split = abs(left - midpoint) <= abs(right - midpoint) ? left : right
    }
    let index = compact.index(compact.startIndex, offsetBy: max(1, min(split, compact.count - 1)))
    return [String(compact[..<index]), String(compact[index...])]
}

func drawHeadline(text: CoverText) {
    let lines = Array(splitHeadline(text.marketingHeadline).prefix(4))
    let maxWidth: CGFloat = 1220
    let maxSize: CGFloat = lines.count >= 4 ? 72 : lines.count == 3 ? 84 : 108
    let minSize: CGFloat = 52
    var headlineSize = maxSize
    while headlineSize > minSize {
        let candidateFont = NSFont(name: "PingFang SC Heavy", size: headlineSize) ?? NSFont.systemFont(ofSize: headlineSize, weight: .heavy)
        let widths = lines.map { ($0 as NSString).size(withAttributes: [.font: candidateFont]).width }
        if (widths.max() ?? 0) <= maxWidth { break }
        headlineSize -= 2
    }
    let font = NSFont(name: "PingFang SC Heavy", size: headlineSize) ?? NSFont.systemFont(ofSize: headlineSize, weight: .heavy)
    let lineHeight = headlineSize * 1.18
    let startY: CGFloat = lines.count == 1 ? 438 : lines.count == 2 ? 476 : lines.count == 3 ? 518 : 552

    for (index, line) in lines.enumerated() {
        let rect = NSRect(x: 78, y: startY - CGFloat(index) * lineHeight, width: maxWidth, height: lineHeight + 12)
        drawOutlinedText(line,
                         rect: rect,
                         font: font,
                         fillColor: NSColor(calibratedRed: 1.0, green: 0.84, blue: 0.12, alpha: 1.0),
                         strokeColor: NSColor.black,
                         strokeRadius: 9,
                         shadowColor: NSColor.black.withAlphaComponent(0.82),
                         shadowBlur: 18)
    }

    let subFont = NSFont(name: "PingFang SC Heavy", size: 58) ?? NSFont.systemFont(ofSize: 58, weight: .heavy)
    drawOutlinedText(text.subhead,
                     rect: NSRect(x: 86, y: 252, width: 1220, height: 84),
                     font: subFont,
                     fillColor: NSColor.white,
                     strokeColor: NSColor(calibratedWhite: 0.08, alpha: 1.0),
                     strokeRadius: 5,
                     shadowColor: NSColor.black.withAlphaComponent(0.7),
                     shadowBlur: 10)
}

func drawChip(_ text: String, rect: NSRect, accent: NSColor) {
    fillRoundedRect(rect, radius: 18, color: NSColor(calibratedWhite: 0.09, alpha: 0.56))
    strokeRoundedRect(rect, radius: 18, color: accent.withAlphaComponent(0.95), lineWidth: 2)
    drawParagraph(text,
                  rect: rect.insetBy(dx: 18, dy: 11),
                  font: NSFont.systemFont(ofSize: 24, weight: .heavy),
                  color: NSColor.white,
                  alignment: .left,
                  lineHeight: 28)
}

func drawStickerCard(image: NSImage) {
    let rect = NSRect(x: 1448, y: 196, width: 336, height: 268)
    guard let context = NSGraphicsContext.current?.cgContext else { return }
    context.saveGState()
    let center = CGPoint(x: rect.midX, y: rect.midY)
    context.translateBy(x: center.x, y: center.y)
    context.rotate(by: 3 * .pi / 180)
    context.translateBy(x: -center.x, y: -center.y)
    context.setShadow(offset: CGSize(width: 0, height: -10), blur: 26, color: NSColor.black.withAlphaComponent(0.42).cgColor)

    fillRoundedRect(rect.insetBy(dx: -4, dy: -4), radius: 24, color: NSColor.white.withAlphaComponent(0.95))
    clipToRoundedRect(rect, radius: 20) {
        drawFillImage(image, in: rect)
        drawGradient(rect, colors: [
            NSColor(calibratedWhite: 1.0, alpha: 0.00),
            NSColor(calibratedWhite: 0.0, alpha: 0.16)
        ], angle: -90)
    }
    strokeRoundedRect(rect, radius: 20, color: NSColor(calibratedRed: 0.95, green: 0.49, blue: 0.72, alpha: 0.95), lineWidth: 3)
    context.restoreGState()
}

func loadLumiImage(pathOverride: String?) -> NSImage? {
    let resolved = expandPath(pathOverride ?? defaultLumiPath)
    guard FileManager.default.fileExists(atPath: resolved) else { return nil }
    return NSImage(contentsOfFile: resolved)
}

func drawLumiBadge(image: NSImage, hasSticker: Bool) {
    let size: CGFloat = hasSticker ? 180 : 208
    let frame = NSRect(
        x: hasSticker ? 1236 : 1512,
        y: hasSticker ? 54 : 72,
        width: size,
        height: size
    )
    guard let context = NSGraphicsContext.current?.cgContext else { return }
    context.saveGState()
    context.setShadow(offset: CGSize(width: 0, height: -10),
                      blur: 26,
                      color: NSColor.black.withAlphaComponent(0.34).cgColor)
    fillRoundedRect(frame.insetBy(dx: -8, dy: -8),
                    radius: (frame.width + 16) / 2,
                    color: NSColor.white.withAlphaComponent(0.95))
    context.restoreGState()

    clipToRoundedRect(frame, radius: frame.width / 2) {
        drawFillImage(image, in: frame, horizontalAlignment: 0.5, verticalAlignment: 0.52)
        drawGradient(frame,
                     colors: [
                        NSColor(calibratedWhite: 1.0, alpha: 0.00),
                        NSColor(calibratedRed: 0.00, green: 0.03, blue: 0.12, alpha: 0.16)
                     ],
                     angle: -90)
    }
    strokeRoundedRect(frame,
                      radius: frame.width / 2,
                      color: NSColor(calibratedRed: 0.95, green: 0.49, blue: 0.72, alpha: 0.95),
                      lineWidth: 4)
}

func drawBottomHints() {
    let y: CGFloat = 70
    let iconColor = NSColor.white.withAlphaComponent(0.86)
    for index in 0..<3 {
        let rect = NSRect(x: 78 + CGFloat(index) * 74, y: y, width: 44, height: 30)
        strokeRoundedRect(rect, radius: 10, color: iconColor, lineWidth: 2)
        if index == 0 {
            let triangle = NSBezierPath()
            triangle.move(to: CGPoint(x: rect.minX + 15, y: rect.minY + 8))
            triangle.line(to: CGPoint(x: rect.maxX - 13, y: rect.midY))
            triangle.line(to: CGPoint(x: rect.minX + 15, y: rect.maxY - 8))
            triangle.close()
            iconColor.setStroke()
            triangle.lineWidth = 2
            triangle.stroke()
        } else if index == 1 {
            let bubble = NSBezierPath(roundedRect: rect.insetBy(dx: 10, dy: 8), xRadius: 8, yRadius: 8)
            bubble.lineWidth = 2
            iconColor.setStroke()
            bubble.stroke()
        } else {
            let clock = NSBezierPath(ovalIn: NSRect(x: rect.midX - 9, y: rect.midY - 9, width: 18, height: 18))
            clock.lineWidth = 2
            iconColor.setStroke()
            clock.stroke()
        }
    }
}

func drawBackground(from candidate: AssetCandidate?) {
    let canvas = NSRect(x: 0, y: 0, width: canvasWidth, height: canvasHeight)
    fillRoundedRect(canvas.insetBy(dx: 14, dy: 14), radius: 34, color: NSColor(calibratedRed: 0.05, green: 0.07, blue: 0.16, alpha: 1.0))

    guard let candidate else {
        fillRoundedRect(canvas.insetBy(dx: 24, dy: 24), radius: 28, color: NSColor(calibratedRed: 0.08, green: 0.10, blue: 0.18, alpha: 1.0))
        return
    }

    let backgroundImage = blurredImage(from: candidate.cgImage, radius: 16) ?? candidate.image
    let drawRect = canvas.insetBy(dx: 24, dy: 24)
    clipToRoundedRect(drawRect, radius: 28) {
        drawFillImage(backgroundImage, in: drawRect, horizontalAlignment: 0.58)
        drawFillImage(candidate.image,
                      in: NSRect(x: drawRect.minX + drawRect.width * 0.26,
                                 y: drawRect.minY + 8,
                                 width: drawRect.width * 0.80,
                                 height: drawRect.height - 16),
                      horizontalAlignment: 0.58,
                      alpha: 0.90)
        drawGradient(drawRect, colors: [
            NSColor(calibratedRed: 0.01, green: 0.02, blue: 0.06, alpha: 0.10),
            NSColor(calibratedRed: 0.01, green: 0.02, blue: 0.06, alpha: 0.36)
        ], angle: -90)
        drawGradient(NSRect(x: drawRect.minX, y: drawRect.minY, width: drawRect.width * 0.72, height: drawRect.height),
                     colors: [
                        NSColor(calibratedRed: 0.01, green: 0.02, blue: 0.06, alpha: 0.82),
                        NSColor(calibratedRed: 0.01, green: 0.02, blue: 0.06, alpha: 0.14)
                     ],
                     angle: 0)
        drawGradient(NSRect(x: drawRect.minX,
                            y: drawRect.minY,
                            width: drawRect.width,
                            height: drawRect.height * 0.36),
                     colors: [
                        NSColor(calibratedRed: 0.00, green: 0.00, blue: 0.02, alpha: 0.44),
                        NSColor(calibratedRed: 0.00, green: 0.00, blue: 0.02, alpha: 0.00)
                     ],
                     angle: 90)
    }

    guard let context = NSGraphicsContext.current?.cgContext else { return }
    context.saveGState()
    context.setShadow(offset: .zero, blur: 24, color: NSColor(calibratedRed: 0.95, green: 0.49, blue: 0.72, alpha: 0.48).cgColor)
    strokeRoundedRect(NSRect(x: 18, y: 18, width: canvasWidth - 36, height: canvasHeight - 36),
                      radius: 32,
                      color: NSColor(calibratedRed: 0.95, green: 0.49, blue: 0.72, alpha: 0.82),
                      lineWidth: 4)
    context.restoreGState()

    let topLine = NSBezierPath()
    topLine.move(to: CGPoint(x: 64, y: 1020))
    topLine.curve(to: CGPoint(x: 1802, y: 1002),
                  controlPoint1: CGPoint(x: 620, y: 1044),
                  controlPoint2: CGPoint(x: 1280, y: 986))
    topLine.lineWidth = 4
    NSColor(calibratedRed: 0.95, green: 0.66, blue: 0.82, alpha: 0.92).setStroke()
    topLine.stroke()
}

func shortDate(_ kicker: String) -> String {
    if let match = kicker.range(of: #"20\d{2}-\d{2}-\d{2}"#, options: .regularExpression) {
        return String(kicker[match])
    }
    return kicker
}

func resolveCoverText(args: [String: String], copy: CopySpec?) -> CoverText {
    let leftLines = splitLines(args["--left-lines"])
    let rightLines = splitLines(args["--right-lines"])
    return CoverText(
        masthead: args["--masthead"] ?? copy?.masthead ?? "科技日报",
        kicker: args["--kicker"] ?? copy?.kicker ?? "Silicon Valley Signals",
        marketingHeadline: args["--marketing-headline"] ?? args["--headline"] ?? copy?.marketingHeadline ?? copy?.headline ?? "AI 信号开始换挡",
        subhead: args["--supporting-headline"] ?? args["--subhead"] ?? copy?.supportingHeadline ?? copy?.subhead ?? "真实热点拼版，不做假概念图",
        leftLine: leftLines.first ?? copy?.leftLines?.first,
        rightLine: rightLines.first ?? copy?.rightLines?.first
    )
}

func makeCover(selected: SelectedAssets, text: CoverText, outPath: String, lumiImage: NSImage?) throws {
    let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: Int(canvasWidth),
        pixelsHigh: Int(canvasHeight),
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    )!
    bitmap.size = NSSize(width: canvasWidth, height: canvasHeight)

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)

    drawBackground(from: selected.background)
    drawNewsCard(text: text)

    if let left = text.leftLine {
        drawChip(left, rect: NSRect(x: 78, y: 604, width: 308, height: 58), accent: NSColor(calibratedRed: 0.33, green: 0.62, blue: 1.0, alpha: 1.0))
    }
    if let right = text.rightLine, selected.sticker != nil {
        drawChip(right, rect: NSRect(x: 1478, y: 540, width: 280, height: 58), accent: NSColor(calibratedRed: 0.94, green: 0.58, blue: 0.36, alpha: 1.0))
    }

    drawHeadline(text: text)

    if let sticker = selected.sticker?.image {
        drawStickerCard(image: sticker)
    }

    if let lumiImage {
        drawLumiBadge(image: lumiImage, hasSticker: selected.sticker != nil)
    }

    drawBottomHints()

    NSGraphicsContext.restoreGraphicsState()

    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "cover", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to encode PNG"])
    }

    let outputURL = URL(fileURLWithPath: expandPath(outPath))
    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try png.write(to: outputURL)
}

let args = parseArguments()
guard let manifestPath = args["--manifest"], let outPath = args["--out"] else {
    fputs(
        "usage: assemble_magazine_cover.swift --manifest <manifest.json> --out <output.png> [--copy-json <cover-copy.json>] [--masthead <text>] [--marketing-headline <text>] [--supporting-headline <text>] [--kicker <text>] [--left-lines <a>] [--right-lines <a>] [--lumi-image <path>] [--max-images <n>]\n",
        stderr
    )
    exit(1)
}

let copySpec = loadCopySpec(args["--copy-json"])
let coverText = resolveCoverText(args: args, copy: copySpec)
let lumiImage = loadLumiImage(pathOverride: args["--lumi-image"])

do {
    let candidates = try loadCandidates(manifestPath: manifestPath)
    let selected = selectAssets(candidates)
    try makeCover(selected: selected, text: coverText, outPath: outPath, lumiImage: lumiImage)
    let payload: [String: Any] = [
        "result": "success",
        "output": expandPath(outPath),
        "background_asset": selected.background?.url.path as Any,
        "sticker_asset": selected.sticker?.url.path as Any,
        "accepted_assets": selected.accepted.map(\.url.path),
        "rejected_assets": selected.rejected.map { ["path": $0.url.path, "reasons": $0.reasons] },
        "marketing_headline": coverText.marketingHeadline,
        "lumi_image": args["--lumi-image"] ?? defaultLumiPath
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
    if let jsonText = String(data: data, encoding: .utf8) {
        print(jsonText)
    }
} catch {
    fputs("assemble_magazine_cover failed: \(error)\n", stderr)
    exit(1)
}
