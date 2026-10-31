"""Recover text from images so it can be labelled untrusted_pixels.

Two passes, as in screenshot-injection detectors: the normal image, and a
contrast-reversed one (finds low-contrast or inverted text). Needs an OCR package:
    pip install rapidocr-onnxruntime pillow
The import is lazy so the rest of AgentGate and its tests work without it.
"""

import io


def extract_text(image_bytes: bytes) -> str:
    try:
        from PIL import Image, ImageOps
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install rapidocr-onnxruntime pillow") from e

    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    engine = RapidOCR()
    seen, lines = set(), []
    for variant in (img, ImageOps.invert(img), ImageOps.autocontrast(img, cutoff=2)):
        result, _ = engine(np.array(variant))
        for item in result or []:
            text = item[1].strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
    return "\n".join(lines)


def label_image(session, image_bytes: bytes, source: str = "screenshot") -> str:
    """OCR the image and record the text in the session as untrusted pixels."""
    text = extract_text(image_bytes)
    session.add_pixels(text, source)
    return text
