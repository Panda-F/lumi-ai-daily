#!/usr/bin/env swift

import AppKit
import Foundation

struct Asset: Decodable {
    let file: String
}

struct Manifest: Decodable {
    let assets: [Asset]
}

struct Slot {
    let x: CGFloat
    let yFromTop: CGFloat
    let width: CGFloat
    let height: CGFloat
}

let canvasWidth: CGFloat = 1920
let canvasHeight: CGFloat = 1080
let titleBandHeight: CGFloat = 220
let margin: CGFloat = 48
let gap: CGFloat = 24

func loadManifest(_ path: String, maxImages: Int) throws -> [URL] {
    let url = URL(fileURLWithPath: NSString(string: path).expandingTildeInPath)
    let data = try Data(contentsOf: url)
    let manifest = try JSONDecoder().decode(Manifest.self, from: data)
    let urls = manifest.assets
        .compactMap { asset -> URL? in
            let candidate = URL(fileURLWithPath: asset.file)
            return FileManager.default.fileExists(atPath: candidate.path) ? candidate : nil
        }
    return Array(urls.prefix(maxImages))
}

func buildSlots(count: Int) -> [Slot] {
    let bodyTop = titleBandHeight + 12
    let bodyHeight = canvasHeight - bodyTop - margin

    if count <= 1 {
        return [Slot(x: margin, yFromTop: bodyTop, width: canvasWidth - margin * 2, height: bodyHeight)]
    }

    if count == 2 {
        let cellWidth = (canvasWidth - margin * 2 - gap) / 2
        return [
            Slot(x: margin, yFromTop: bodyTop, width: cellWidth, height: bodyHeight),
            Slot(x: margin + cellWidth + gap, yFromTop: bodyTop, width: cellWidth, height: bodyHeight)
        ]
    }

    if count == 3 {
        let leftWidth: CGFloat = 1160
        let rightWidth = canvasWidth - margin * 2 - gap - leftWidth
        let rightHeight = (bodyHeight - gap) / 2
        return [
            Slot(x: margin, yFromTop: bodyTop, width: leftWidth, height: bodyHeight),
            Slot(x: margin + leftWidth + gap, yFromTop: bodyTop, width: rightWidth, height: rightHeight),
            Slot(x: margin + leftWidth + gap, yFromTop: bodyTop + rightHeight + gap, width: rightWidth, height: rightHeight)
        ]
    }

    if count == 4 {
        let cellWidth = (canvasWidth - margin * 2 - gap) / 2
        let cellHeight = (bodyHeight - gap) / 2
        return [
            Slot(x: margin, yFromTop: bodyTop, width: cellWidth, height: cellHeight),
            Slot(x: margin + cellWidth + gap, yFromTop: bodyTop, width: cellWidth, height: cellHeight),
            Slot(x: margin, yFromTop: bodyTop + cellHeight + gap, width: cellWidth, height: cellHeight),
            Slot(x: margin + cellWidth + gap, yFromTop: bodyTop + cellHeight + gap, width: cellWidth, height: cellHeight)
        ]
    }

    let cellWidth = (canvasWidth - margin * 2 - gap * 2) / 3
    let cellHeight = (bodyHeight - gap) / 2
    var slots: [Slot] = []
    for row in 0..<2 {
        for col in 0..<3 {
            slots.append(
                Slot(
                    x: margin + CGFloat(col) * (cellWidth + gap),
                    yFromTop: bodyTop + CGFloat(row) * (cellHeight + gap),
                    width: cellWidth,
                    height: cellHeight
                )
            )
        }
    }
    return Array(slots.prefix(count))
}

func toCanvasRect(slot: Slot) -> NSRect {
    let y = canvasHeight - slot.yFromTop - slot.height
    return NSRect(x: slot.x, y: y, width: slot.width, height: slot.height)
}

func drawFillImage(_ image: NSImage, in rect: NSRect) {
    let imageSize = image.size
    guard imageSize.width > 0, imageSize.height > 0 else { return }

    let destRatio = rect.width / rect.height
    let imageRatio = imageSize.width / imageSize.height

    var sourceRect = NSRect(origin: .zero, size: imageSize)
    if imageRatio > destRatio {
        let newWidth = imageSize.height * destRatio
        sourceRect.origin.x = (imageSize.width - newWidth) / 2
        sourceRect.size.width = newWidth
    } else {
        let newHeight = imageSize.width / destRatio
        sourceRect.origin.y = (imageSize.height - newHeight) / 2
        sourceRect.size.height = newHeight
    }

    image.draw(in: rect, from: sourceRect, operation: .sourceOver, fraction: 1.0)
}

func drawText(_ text: String, at point: NSPoint, font: NSFont, color: NSColor) {
    let attrs: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color
    ]
    (text as NSString).draw(at: point, withAttributes: attrs)
}

func makeImage(title: String, subtitle: String, assets: [URL], outPath: String) throws {
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
    guard let context = NSGraphicsContext.current?.cgContext else {
        throw NSError(domain: "collage", code: 1, userInfo: [NSLocalizedDescriptionKey: "Failed to create graphics context"])
    }

    NSColor(calibratedRed: 0.03, green: 0.08, blue: 0.15, alpha: 1.0).setFill()
    context.fill(CGRect(x: 0, y: 0, width: canvasWidth, height: canvasHeight))

    NSColor(calibratedRed: 0.05, green: 0.13, blue: 0.22, alpha: 1.0).setFill()
    context.fill(CGRect(x: 0, y: canvasHeight - titleBandHeight, width: canvasWidth, height: titleBandHeight))

    NSColor(calibratedRed: 0.24, green: 0.86, blue: 1.0, alpha: 1.0).setFill()
    context.fill(CGRect(x: margin, y: canvasHeight - titleBandHeight + 18, width: canvasWidth - margin * 2, height: 3))

    let titleFont = NSFont(name: "PingFang SC Semibold", size: 96) ?? NSFont.boldSystemFont(ofSize: 96)
    let subtitleFont = NSFont(name: "PingFang SC Medium", size: 28) ?? NSFont.systemFont(ofSize: 28, weight: .medium)
    drawText(title, at: NSPoint(x: margin, y: canvasHeight - 156), font: titleFont, color: .white)
    if !subtitle.isEmpty {
        drawText(
            subtitle,
            at: NSPoint(x: margin, y: canvasHeight - 196),
            font: subtitleFont,
            color: NSColor(calibratedRed: 0.60, green: 0.74, blue: 0.82, alpha: 1.0)
        )
    }

    let slots = buildSlots(count: assets.count)
    for (assetURL, slot) in zip(assets, slots) {
        let rect = toCanvasRect(slot: slot)
        NSColor(calibratedRed: 0.09, green: 0.20, blue: 0.29, alpha: 1.0).setFill()
        context.fill(rect.insetBy(dx: -2, dy: -2))
        if let image = NSImage(contentsOf: assetURL) {
            drawFillImage(image, in: rect)
        }
    }

    NSColor(calibratedRed: 0.24, green: 0.86, blue: 1.0, alpha: 1.0).setFill()
    context.fill(CGRect(x: 0, y: 0, width: canvasWidth, height: 8))

    NSGraphicsContext.restoreGraphicsState()

    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "collage", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to encode PNG"])
    }
    let outputURL = URL(fileURLWithPath: NSString(string: outPath).expandingTildeInPath)
    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try png.write(to: outputURL)
}

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

let args = parseArguments()
guard let manifestPath = args["--manifest"], let outPath = args["--out"] else {
    fputs("usage: assemble_story_collage.swift --manifest <manifest.json> --out <output.png> [--title <text>] [--subtitle <text>] [--max-images <n>]\n", stderr)
    exit(1)
}

let title = args["--title"] ?? "AI速递"
let subtitle = args["--subtitle"] ?? ""
let maxImages = Int(args["--max-images"] ?? "6") ?? 6

do {
    let assets = try loadManifest(manifestPath, maxImages: maxImages)
    try makeImage(title: title, subtitle: subtitle, assets: assets, outPath: outPath)
    let payload: [String: Any] = [
        "result": "success",
        "output": outPath,
        "asset_count": assets.count,
        "assets": assets.map(\.path)
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
    if let text = String(data: data, encoding: .utf8) {
        print(text)
    }
} catch {
    fputs("assemble_story_collage failed: \(error)\n", stderr)
    exit(1)
}
