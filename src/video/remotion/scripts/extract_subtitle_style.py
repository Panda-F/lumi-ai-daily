#!/usr/bin/env python3

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import numpy as np


@dataclass
class Box:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)


def parse_box(value: str) -> Box:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("Box must be x1,y1,x2,y2")
    return Box(*parts)


def default_box(width: int, height: int) -> Box:
    return Box(int(width * 0.38), int(height * 0.82), int(width * 0.995), int(height * 0.998))


def default_reference(box: Box) -> Box:
    ref_width = max(180, int(box.width * 0.14))
    return Box(max(0, box.x1 - ref_width), box.y1, box.x1, box.y2)


def crop_rgb(image: np.ndarray, box: Box) -> np.ndarray:
    return image[box.y1:box.y2, box.x1:box.x2, :3]


def rgb_mean(pixels: np.ndarray) -> np.ndarray:
    return pixels.reshape(-1, 3).mean(axis=0)


def masked_mean(pixels: np.ndarray, bright_threshold: int) -> np.ndarray:
    luminance = 0.2126 * pixels[:, :, 0] + 0.7152 * pixels[:, :, 1] + 0.0722 * pixels[:, :, 2]
    mask = luminance < bright_threshold
    if mask.sum() < 50:
        return rgb_mean(pixels)
    return pixels[mask].mean(axis=0)


def estimate_overlay(inside_rgb: np.ndarray, reference_rgb: np.ndarray) -> tuple[float, float]:
    best_error = None
    best_alpha = 0.74
    best_gray = float(np.mean(inside_rgb))

    for alpha in np.linspace(0.2, 0.95, 751):
        gray = float(np.mean((inside_rgb - (1 - alpha) * reference_rgb) / alpha))
        gray = float(np.clip(gray, 0, 255))
        predicted = alpha * gray + (1 - alpha) * reference_rgb
        error = float(np.mean((predicted - inside_rgb) ** 2))
        if best_error is None or error < best_error:
            best_error = error
            best_alpha = float(alpha)
            best_gray = gray

    return best_gray, best_alpha


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate subtitle panel color and opacity from a reference frame.")
    parser.add_argument("image", help="Path to the reference image.")
    parser.add_argument("--box", type=parse_box, help="Subtitle box region as x1,y1,x2,y2.")
    parser.add_argument("--reference", type=parse_box, help="Nearby background region as x1,y1,x2,y2.")
    parser.add_argument("--bright-threshold", type=int, default=210, help="Exclude bright subtitle glyph pixels.")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    image = np.array(Image.open(image_path).convert("RGBA"), dtype=np.float32)
    height, width = image.shape[:2]

    box = args.box or default_box(width, height)
    reference = args.reference or default_reference(box)

    box_rgb = crop_rgb(image, box)
    reference_rgb = crop_rgb(image, reference)

    inside_mean = masked_mean(box_rgb, args.bright_threshold)
    reference_mean = rgb_mean(reference_rgb)
    gray, alpha = estimate_overlay(inside_mean, reference_mean)

    output = {
        "image": str(image_path),
        "box": box.__dict__,
        "reference": reference.__dict__,
        "inside_rgb": [round(float(value), 2) for value in inside_mean],
        "reference_rgb": [round(float(value), 2) for value in reference_mean],
        "estimated_overlay_gray": round(gray, 2),
        "estimated_alpha": round(alpha, 3),
        "css_rgba": f"rgba({int(round(gray))}, {int(round(gray))}, {int(round(gray))}, {alpha:.3f})"
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
