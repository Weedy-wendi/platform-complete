"""Visual screenshot comparison (FUN-04).

Screenshots may be large; only artifact ids are stored in MySQL. This module
works on decoded grayscale pixels so it has no Pillow dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import InvalidArgumentError


@dataclass(frozen=True)
class ImageData:
    width: int
    height: int
    pixels: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise InvalidArgumentError("image dimensions must be positive")
        if len(self.pixels) != self.width * self.height:
            raise InvalidArgumentError("pixel count does not match image dimensions")


@dataclass(frozen=True)
class VisualDiffResult:
    passed: bool
    mismatch_ratio: float
    diff_pixels: int
    total_pixels: int
    diff_image: tuple[int, ...] = ()


def compare_images(expected: ImageData, actual: ImageData, *, threshold: float = 0.01) -> VisualDiffResult:
    if expected.width != actual.width or expected.height != actual.height:
        raise InvalidArgumentError("image dimensions must match")
    if not 0.0 <= threshold <= 1.0:
        raise InvalidArgumentError("threshold must be between 0 and 1")
    diff: list[int] = []
    mismatched = 0
    for left, right in zip(expected.pixels, actual.pixels, strict=True):
        if left != right:
            mismatched += 1
            diff.append(255)
        else:
            diff.append(0)
    total = expected.width * expected.height
    ratio = mismatched / total if total else 0.0
    return VisualDiffResult(
        passed=ratio <= threshold,
        mismatch_ratio=ratio,
        diff_pixels=mismatched,
        total_pixels=total,
        diff_image=tuple(diff),
    )


__all__ = ["ImageData", "VisualDiffResult", "compare_images"]
