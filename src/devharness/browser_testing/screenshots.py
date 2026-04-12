"""Screenshot capture and baseline diffing for visual regression."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ScreenshotManager:
    """Manage screenshot baselines and visual diffs."""

    def __init__(self, baselines_dir: str = ".devharness/baselines") -> None:
        self._baselines_dir = Path(baselines_dir)

    def save_baseline(self, name: str, screenshot_path: str) -> None:
        """Save a screenshot as the baseline for future comparisons."""
        self._baselines_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(screenshot_path, self._baselines_dir / f"{name}.png")

    def compare_to_baseline(self, name: str, screenshot_path: str) -> dict:
        """Compare a screenshot against its baseline.

        Returns a dict with 'matches' (bool) and 'diff_percentage' (float).
        Uses Pillow for pixel comparison if available.
        """
        baseline_path = self._baselines_dir / f"{name}.png"
        if not baseline_path.exists():
            return {"matches": True, "diff_percentage": 0.0, "no_baseline": True}

        try:
            from PIL import Image
            import io

            baseline = Image.open(baseline_path)
            current = Image.open(screenshot_path)

            if baseline.size != current.size:
                return {"matches": False, "diff_percentage": 100.0, "reason": "size_mismatch"}

            # Pixel-by-pixel comparison
            diff_count = 0
            total_pixels = baseline.size[0] * baseline.size[1]

            b_pixels = list(baseline.getdata())
            c_pixels = list(current.getdata())

            for bp, cp in zip(b_pixels, c_pixels):
                if bp != cp:
                    diff_count += 1

            diff_pct = (diff_count / total_pixels) * 100 if total_pixels > 0 else 0.0
            return {
                "matches": diff_pct < 1.0,  # allow <1% pixel difference
                "diff_percentage": round(diff_pct, 2),
            }

        except ImportError:
            logger.warning("Pillow not installed -- skipping visual regression")
            return {"matches": True, "diff_percentage": 0.0, "pillow_missing": True}
