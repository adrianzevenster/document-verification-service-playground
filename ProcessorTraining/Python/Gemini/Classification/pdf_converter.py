import fitz

def pdf_to_images(pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:   # ⬅ rename here
    """Convert a PDF (bytes) into a list of PNG bytes, one per page."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_pixmap(dpi=dpi).tobytes("png") for page in doc]