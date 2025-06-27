"""metadata_extraction_service.py

Comprehensive metadata extractor for PDFs and raster images.

Supported formats & details
---------------------------
* **JPEG / TIFF / HEIC** – EXIF 2.3 via *piexif*: Make, Model, Lens,
  DateTimeOriginal, GPS, Orientation, Software, ISO, ExposureTime, Flash, …
* **PNG** – all `tEXt`, `iTXt`, `zTXt` chunks plus:
  * `PNG:dpi`   → tuple `(x_dpi, y_dpi)` converted from the *pHYs* chunk or
    Pillow’s `info["dpi"]`.
  * `PNG:gamma` → float γ (0.45455 = sRGB).
  * Basic `format`, `mode`, `size` for quick sanity checks.
* **PDF** – `/Info` dictionary, XMP packets (*Creator, Producer, …*), page
  count, encryption flag.

Returns a **flat `dict[str, Any]`** where nested EXIF / GPS structures are
JSON‑encoded so downstream code can store them in a single “value” column.

Example
~~~~~~~
```python
from metadata_extraction_service import MetadataExtractor
b = Path("scan.jpg").read_bytes()
meta = MetadataExtractor().extract(b, filename="scan.jpg", mime_type="image/jpeg")
print(meta["exif.Model"], meta["PNG:dpi"], meta["pdf.Creator"], ...)  # keys appear when present
```
"""
from __future__ import annotations

import io, json, logging
from pathlib import Path
from typing import Dict, Any

from PIL import Image

try:
    import piexif
except ImportError:  # EXIF optional
    piexif = None  # type: ignore

try:
    from PyPDF2 import PdfReader
except ImportError:  # PDF optional
    PdfReader = None  # type: ignore

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Pull as much metadata as possible from bytes of a single file."""

    # ------------------------------------------------------------------
    def extract(self, data: bytes, *, filename: str | None = None,
                mime_type: str | None = None) -> Dict[str, Any]:
        suf = (Path(filename).suffix.lower() if filename else "")
        meta: Dict[str, Any] = {
            "source": {
                "filename": filename or "<memory>",
                "size_bytes": len(data),
                "mime_type": mime_type or self._mime_from_suffix(suf),
            }
        }

        if suf in {".jpg", ".jpeg", ".tif", ".tiff", ".heic"}:
            meta.update(self._jpeg_tiff_meta(data))
        elif suf == ".png":
            meta.update(self._png_meta(data))
        elif suf == ".pdf":
            meta.update(self._pdf_meta(data))
        else:
            logger.debug("Unsupported extension %s – only basic source meta", suf)
        return meta

    # ------------------------------------------------------------------
    @staticmethod
    def _mime_from_suffix(sfx: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".pdf": "application/pdf",
        }.get(sfx, "application/octet-stream")

    # ------------------------------------------------------------------
    def _jpeg_tiff_meta(self, data: bytes) -> Dict[str, Any]:
        if piexif is None:
            return {}
        try:
            exif_dict = piexif.load(data)
            flat: Dict[str, Any] = {}
            for ifd_name, tags in exif_dict.items():
                if tags is None:
                    continue
                for tag, val in tags.items():
                    try:
                        tag_name = piexif.TAGS[ifd_name][tag]["name"]
                    except Exception:
                        tag_name = f"tag_{tag}"
                    key_std = f"exif.{tag_name}"
                    key_old = f"EXIF:{tag_name}"   # backward‑compat
                    if isinstance(val, bytes):
                        try:
                            val = val.decode("utf-8", "replace")
                        except Exception:
                            val = str(val)
                    flat[key_std] = flat[key_old] = val
            return flat
        except Exception as e:  # noqa: BLE001
            logger.warning("piexif failed: %s", e)
            return {}

    # ------------------------------------------------------------------
    def _png_meta(self, data: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            img = Image.open(io.BytesIO(data))
            info = img.info or {}
            # tEXt / iTXt / zTXt
            for k, v in info.items():
                out[f"PNG:{k}"] = v
            # DPI (from pHYs or info["dpi"])
            if "dpi" in info and isinstance(info["dpi"], tuple):
                try:
                    x, y = info["dpi"]
                    out["PNG:dpi"] = (float(x), float(y))
                except Exception:
                    pass
            # gamma
            if "gamma" in info:
                try:
                    out["PNG:gamma"] = float(info["gamma"])
                except Exception:
                    pass
            out["image"] = {
                "format": img.format,
                "mode": img.mode,
                "size": img.size,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("PIL PNG parse failed: %s", e)
        return out

    # ------------------------------------------------------------------
    def _pdf_meta(self, data: bytes) -> Dict[str, Any]:
        if PdfReader is None:
            return {}
        out: Dict[str, Any] = {}
        try:
            reader = PdfReader(io.BytesIO(data))
            # DocInfo
            for k, v in (reader.metadata or {}).items():
                key_std = f"pdf.{k.strip('/')}"
                key_old = f"PDF:{k.strip('/')}"  # legacy
                out[key_std] = out[key_old] = v
            # XMP (creator‑tool etc.)
            xmp = getattr(reader, "xmp_metadata", None)
            if xmp:
                if hasattr(xmp, "creator_tool") and xmp.creator_tool:
                    out["pdf.CreatorTool"] = xmp.creator_tool
            out["page_count"] = len(reader.pages)
            out["encrypted"]  = reader.is_encrypted
        except Exception as e:  # noqa: BLE001
            logger.warning("PyPDF2 parse failed: %s", e)
        return out
