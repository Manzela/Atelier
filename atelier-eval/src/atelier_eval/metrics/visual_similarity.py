"""Visual similarity metrics for frontend code quality evaluation.

Uses SSIM (Structural Similarity Index Measure) from scikit-image.
SSIM is preferred over pixel MSE because it correlates better with
human perceptual quality (Wang et al. 2004).
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np  # noqa: TC002
import numpy.typing as npt  # noqa: TC002


def render_html_to_screenshot(
    html: str,
    *,
    width: int = 1280,
    height: int = 800,
) -> bytes:
    """Render HTML string to a PNG screenshot via headless Chromium.

    Returns raw PNG bytes.

    Raises:
        subprocess.CalledProcessError: if chromium exits non-zero.
        FileNotFoundError: if chromium-browser is not in PATH.
    """
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write(html)
        html_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as out:
        screenshot_path = out.name

    try:
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "chromium-browser",
                "--headless",
                "--no-sandbox",
                f"--window-size={width},{height}",
                f"--screenshot={screenshot_path}",
                f"file://{html_path}",
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return Path(screenshot_path).read_bytes()
    finally:
        Path(html_path).unlink(missing_ok=True)
        Path(screenshot_path).unlink(missing_ok=True)


def compute_ssim(generated_png: bytes, reference_path: str) -> float:
    """Compute SSIM between a generated PNG (bytes) and a reference PNG file.

    Returns a float in [0.0, 1.0]. Higher is more similar.
    """
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    from skimage.metrics import (  # noqa: PLC0415
        structural_similarity as ssim_fn,
    )

    gen_img: npt.NDArray[np.uint8] = np.array(
        Image.open(io.BytesIO(generated_png)).convert("RGB"),
    )
    ref_img: npt.NDArray[np.uint8] = np.array(
        Image.open(reference_path).convert("RGB"),
    )

    # Resize to same dimensions (use generated as target size)
    if gen_img.shape != ref_img.shape:
        ref_pil = Image.fromarray(ref_img).resize(
            (gen_img.shape[1], gen_img.shape[0]),
            Image.LANCZOS,
        )
        ref_img = np.array(ref_pil)

    score: float = ssim_fn(
        gen_img,
        ref_img,
        channel_axis=2,
        data_range=255,
    )
    return float(score)
