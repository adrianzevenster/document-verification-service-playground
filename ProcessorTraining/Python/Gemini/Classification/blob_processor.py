import os
from google.cloud.storage.blob import Blob
from .pdf_converter      import pdf_to_images
from .gemini_classifier  import GeminiClassifier
from .gemini_extractor   import GeminiExtractor

class BlobProcessor:
    """Downloads a blob, classifies doc type (once), then extracts entities per page."""

    def __init__(self, extractor: GeminiExtractor, classifier: GeminiClassifier):
        self.extractor  = extractor
        self.classifier = classifier

    def process(self, blob: Blob) -> tuple[str, list[dict]]:
        data  = blob.download_as_bytes()
        ext   = os.path.splitext(blob.name)[1].lower()
        pages = pdf_to_images(data) if ext == ".pdf" else [data]

        # -------- classify on first page -------- #
        doc_type = self.classifier.classify(pages[0])
        print(f"[BlobProcessor] {blob.name} -> {doc_type}")

        # -------- extract entities page-by-page -------- #
        out: list[dict] = []
        for idx, img in enumerate(pages, start=1):
            try:
                ents = self.extractor.call(img)
            except Exception as e:
                print(f"  ! extraction error on page {idx}: {e}")
                continue
            for ent in ents:
                ent["page"]          = idx
                ent["document_type"] = doc_type
            out.extend(ents)
        return doc_type, out
