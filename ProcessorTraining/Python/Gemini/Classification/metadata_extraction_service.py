"""metadata_extraction_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Extract **every piece of metadata we can sensibly reach** from PDFs and common
image formats (JPEG, PNG, TIFF) and write it to JSON or CSV.

The module behaves just like the other pluggable helpers in this code‑base:

* `MetadataExtractor` – library class with `extract()` and `to_file()` helpers.
* CLI: `python -m metadata_extraction_service extract my.pdf --out meta.json`

Dependencies (all lightweight, pure‑Python):
    pip install pypdf pillow piexif

If any lib is missing at runtime we gracefully degrade (PDF without PyPDF2 →
only basic file stats; images without Pillow → no EXIF, etc.).
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

try:
    import piexif  # type: ignore
except ImportError:  # pragma: no cover
    piexif = None  # type: ignore

class MetadataExtractor:
    """Extract metadata from a PDF or image given raw bytes."""

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict

    def extract(self, file_bytes: bytes, *, filename: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """Return a dict with *all* metadata we can parse.

        Keys follow this convention:
        * top‑level `source`   – original file name, size, mime_type
        * `pdf`, `image`       – medium‑specific nested metadata
        * unknown/unsupported files ⇒ only `source` returned
        """
        mime_type = mime_type or _guess_mime(filename)
        meta: Dict[str, Any] = {
            "source": {
                "filename": filename,
                "size_bytes": len(file_bytes),
                "mime_type": mime_type,
            }
        }

        if mime_type == "application/pdf":
            pdf_meta = self._extract_pdf(file_bytes)
            if pdf_meta:
                meta["pdf"] = pdf_meta
        elif mime_type.startswith("image/"):
            img_meta = self._extract_image(file_bytes, mime_type)
            if img_meta:
                meta["image"] = img_meta
        else:
            if self.strict:
                raise ValueError(f"Unsupported mime‑type: {mime_type}")
        return meta

    def to_file(self, metadata: Dict[str, Any], out_path: Path, *, fmt: str = "json") -> None:
        """Write metadata to `out_path` (JSON or CSV)."""
        fmt = fmt.lower()
        if fmt == "json":
            out_path.write_text(json.dumps(metadata, indent=2, default=str))
        elif fmt == "csv":
            import csv  # lazy import

            flat: Dict[str, Any] = {}
            for section, section_data in metadata.items():
                if isinstance(section_data, dict):
                    for k, v in section_data.items():
                        flat[f"{section}_{k}"] = v
                else:
                    flat[section] = section_data
            with out_path.open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=flat.keys())
                writer.writeheader()
                writer.writerow(flat)
        else:
            raise ValueError("Unsupported output format – choose 'json' or 'csv'")


    def _extract_pdf(self, file_bytes: bytes) -> Dict[str, Any]:
        if PdfReader is None:
            return {"warning": "pypdf not installed"}
        reader = PdfReader(io.BytesIO(file_bytes))
        info = reader.metadata or {}
        xmp = reader.xmp_metadata

        pdf_meta = {k[1:]: v for k, v in info.items()}  # strip leading slash
        pdf_meta["pages"] = len(reader.pages)
        if xmp:
            pdf_meta["xmp_raw"] = str(xmp)
        return pdf_meta

    def _extract_image(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        if Image is None:
            return {"warning": "Pillow not installed"}
        with Image.open(io.BytesIO(file_bytes)) as img:
            meta: Dict[str, Any] = {
                "format": img.format,
                "mode": img.mode,
                "size": img.size,  # (w, h)
            }

            if img.format in {"JPEG", "TIFF"} and piexif is not None:
                try:
                    exif_dict = piexif.load(img.info.get("exif", b""))
                    # flatten exif into human‑readable keys
                    meta["exif"] = {
                        _tag_name_ify(tag, ifd): exif_dict[ifd][tag]
                        for ifd in exif_dict for tag in exif_dict[ifd]
                    }
                except Exception as exc:  # pragma: no cover – lenient
                    meta["exif_error"] = str(exc)
        return meta

def _tag_name_ify(tag: int, ifd: str) -> str:
    """Convert a numeric EXIF tag + IFD into a readable string."""
    try:
        import piexif
        name = piexif.TAGS[ifd][tag]["name"]
        return f"{ifd}_{name}"
    except Exception:  # pragma: no cover
        return f"{ifd}_{tag}"


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _cli_extract(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(2)

    mime_type = args.mime_type or _guess_mime(path.name)
    extractor = MetadataExtractor(strict=False)
    meta = extractor.extract(path.read_bytes(), filename=path.name, mime_type=mime_type)

    out_path = Path(args.out or (path.stem + (".json" if args.format == "json" else ".csv")))
    extractor.to_file(meta, out_path, fmt=args.format)
    print(f"Metadata written → {out_path}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract metadata from PDF / images")
    p.add_argument("file", help="Input PDF or image path")
    p.add_argument("--mime-type", help="Override detected MIME type")
    p.add_argument("--out", help="Output file path (defaults to <input>.json/csv)")
    p.add_argument("--format", choices=["json", "csv"], default="json")
    p.set_defaults(func=_cli_extract)
    return p


if __name__ == "__main__":
    _cli_extract(_build_parser().parse_args())