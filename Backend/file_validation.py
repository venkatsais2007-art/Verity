import os
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_PIXELS = 20_000_000
IMAGE_EXTENSIONS = {
    "PNG": {".png"},
    "JPEG": {".jpg", ".jpeg"},
    "WEBP": {".webp"},
}


def validate_image(data, filename=None):
    extension = os.path.splitext(filename or "")[1].lower()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                width, height = image.size
                if image_format not in IMAGE_EXTENSIONS:
                    raise ValueError("Only PNG, JPEG, and WEBP images are supported.")
                if filename and extension not in IMAGE_EXTENSIONS[image_format]:
                    raise ValueError("The file extension does not match the image content.")
                if width < 8 or height < 8 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions must be at least 8x8 and no more than 20 megapixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not supported.")
                image.verify()
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("The uploaded file is not a valid supported image.") from exc
    return width, height
