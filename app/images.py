import io
import warnings

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def decode_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Each image must be between 1 byte and 15 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Use a JPEG, PNG, or WebP image.")
                if image.width * image.height > MAX_PIXELS or min(image.size) < 128:
                    raise ValueError("Images must be at least 128 × 128 and no more than 24 megapixels.")
                image.load()
                image = ImageOps.exif_transpose(image)
                rgba = image.convert("RGBA")
                base = Image.new("RGBA", image.size, "white")
                base.alpha_composite(rgba)
                rgb = base.convert("RGB")
                rgb.info.clear()
                return rgb
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("This file is not a valid, supported image.") from exc


def preserve_regions(original, generated, original_labels, generated_labels, editable_ids, identity_ids):
    """Composite only a garment/body envelope; lock original identity and distant background.

    Segmentation accuracy determines protection quality. Pose is conditioned by the model,
    not guaranteed by this compositing step. Output keeps the source pixel dimensions.
    """
    generated = generated.resize(original.size, Image.Resampling.LANCZOS)
    source = np.asarray(original_labels)
    target = np.asarray(generated_labels)
    source = np.array(Image.fromarray(source.astype("uint8")).resize(original.size, Image.Resampling.NEAREST))
    target = np.array(Image.fromarray(target.astype("uint8")).resize(original.size, Image.Resampling.NEAREST))
    edit = (np.isin(source, editable_ids) | np.isin(target, editable_ids)).astype("uint8") * 255
    if not edit.any():
        raise ValueError("No editable garment region was detected. Try a clear, front-facing model photo.")
    radius = max(1, round(min(original.size) / 150))
    mask = Image.fromarray(edit).filter(ImageFilter.MaxFilter(radius * 2 + 1))
    mask = mask.filter(ImageFilter.GaussianBlur(radius))
    alpha = np.array(mask)
    alpha[np.isin(source, identity_ids)] = 0
    return Image.composite(generated, original, Image.fromarray(alpha))
