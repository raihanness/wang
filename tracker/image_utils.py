import io
import os
from PIL import Image, ImageOps
from django.core.files.base import ContentFile


def optimize_receipt_image(image_field_or_file, max_dim=1200, quality=82):
    """
    Resizes image to fit within max_dim x max_dim (preserving aspect ratio),
    auto-corrects EXIF rotation, and encodes as optimized WebP.
    Returns a ContentFile with a .webp extension.
    """
    if not image_field_or_file:
        return image_field_or_file

    try:
        f = getattr(image_field_or_file, "file", image_field_or_file)
        if hasattr(f, "seek"):
            f.seek(0)

        img = Image.open(f)

        # Transpose based on EXIF orientation (e.g. mobile camera photos)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Ensure supported color mode for WebP
        if img.mode in ("RGBA", "LA", "PA"):
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize proportionally if exceeding max dimensions
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # Encode to WebP buffer
        out_buf = io.BytesIO()
        img.save(out_buf, format="WEBP", quality=quality, method=6)
        out_buf.seek(0)
        try:
            img.close()
        except Exception:
            pass

        # Build clean filename with .webp extension
        raw_name = getattr(image_field_or_file, "name", "receipt.webp") or "receipt.webp"
        base_name, _ = os.path.splitext(os.path.basename(raw_name))
        clean_name = f"{base_name}.webp"

        return ContentFile(out_buf.getvalue(), name=clean_name)
    except Exception:
        # Fallback to original file on any unexpected error
        if hasattr(image_field_or_file, "seek"):
            try:
                image_field_or_file.seek(0)
            except Exception:
                pass
        return image_field_or_file


def delete_file_safely(field_file):
    """
    Safely closes and deletes a storage file, guarding against Windows file locks.
    """
    if not field_file:
        return
    try:
        field_file.close()
    except Exception:
        pass

    try:
        storage = getattr(field_file, "storage", None)
        name = getattr(field_file, "name", None)
        if storage and name and storage.exists(name):
            storage.delete(name)
    except Exception:
        try:
            field_file.delete(save=False)
        except Exception:
            pass

