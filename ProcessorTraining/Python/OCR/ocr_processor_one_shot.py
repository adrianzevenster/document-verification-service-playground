import csv
import logging
import time
from dataclasses import dataclass
from typing import List

from google.cloud import storage, documentai_v1 as documentai
from google.oauth2 import service_account


# ─── CONFIGURATION ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class OCRConfig:
    project_id: str = "1027521807"
    location: str = "us"
    processor_id: str = "474b98a3e9d41efd"
    bucket_name: str = "adg-delivery-moniepoint-docs-bucket-001"
    prefix: str = "training-documents/"
    output_csv: str = "../Outputs/OCR/all_text_with_positions.csv"
    key_path: str = "../../.gcp/adg-documentai-sa-key.json"
    time_format: str = "%Y-%m-%d %H:%M:%S"


class MimeTypeResolver:
    """Resolve file extensions to MIME types."""
    _mapping = {
        'png':  'image/png',
        'jpg':  'image/jpeg',
        'jpeg': 'image/jpeg',
        'pdf':  'application/pdf',
        'tif':  'image/tiff',
        'tiff': 'image/tiff',
    }

    @staticmethod
    def get_mime_type(filename: str) -> str:
        ext = filename.lower().split('.')[-1]
        return MimeTypeResolver._mapping.get(ext, 'application/octet-stream')


@dataclass
class WordRecord:
    gcs_uri: str
    page_num: int
    line_num: int
    word_pos: int
    text: str
    confidence: float


class DocumentAIClient:
    """Wrapper for Document AI processing."""

    def __init__(self, config: OCRConfig):
        creds = service_account.Credentials.from_service_account_file(config.key_path)
        self.client = documentai.DocumentProcessorServiceClient(
            credentials=creds,
            client_options={"api_endpoint": f"{config.location}-documentai.googleapis.com:443"},
        )
        self.processor_path = self.client.processor_path(
            config.project_id, config.location, config.processor_id
        )

    def process_blob(self, content: bytes, mime_type: str) -> documentai.Document:
        request = documentai.ProcessRequest(
            name=self.processor_path,
            raw_document=documentai.RawDocument(
                content=content,
                mime_type=mime_type,
            ),
        )
        return self.client.process_document(request=request).document


class OCRExtractor:
    """Extract words and positions from processed Document AI output."""

    @staticmethod
    def extract_records(gcs_uri: str, document: documentai.Document) -> List[WordRecord]:
        full_text = document.text or ''
        records: List[WordRecord] = []

        for p_idx, page in enumerate(document.pages, start=1):
            for l_idx, line in enumerate(page.lines, start=1):
                # extract full line text
                segments = line.layout.text_anchor.text_segments or []
                line_text = ''.join(
                    full_text[int(s.start_index or 0): int(s.end_index or len(full_text))]
                    for s in segments
                ).strip()
                line_conf = line.layout.confidence or 0.0

                for w_idx, word in enumerate(line_text.split(), start=1):
                    records.append(
                        WordRecord(
                            gcs_uri=gcs_uri,
                            page_num=p_idx,
                            line_num=l_idx,
                            word_pos=w_idx,
                            text=word,
                            confidence=line_conf,
                        )
                    )
        return records


class CSVExporter:
    """Write records to CSV."""

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.file = open(self.output_path, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow([
            'gcs_uri', 'page_num', 'line_num', 'word_pos', 'word_text', 'line_confidence'
        ])

    def write(self, records: List[WordRecord]):
        for rec in records:
            self.writer.writerow([
                rec.gcs_uri,
                rec.page_num,
                rec.line_num,
                rec.word_pos,
                rec.text,
                f"{rec.confidence:.2f}",
            ])

    def close(self):
        self.file.close()


class OCRPipeline:
    """Runs the full OCR extraction pipeline."""

    def __init__(self, config: OCRConfig):
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s",
                            datefmt=config.time_format)
        self.config = config
        self.storage = storage.Client(project=config.project_id,
                                      credentials=service_account.Credentials.from_service_account_file(
                                          config.key_path))
        self.ai_client = DocumentAIClient(config)
        self.exporter = CSVExporter(config.output_csv)

    def run(self) -> None:
        bucket = self.storage.bucket(self.config.bucket_name)
        blobs = bucket.list_blobs(prefix=self.config.prefix)

        for blob in blobs:
            if blob.name.endswith('/') or not blob.name.lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.pdf', '.tiff', '.tif')):
                continue

            gcs_uri = f"gs://{self.config.bucket_name}/{blob.name}"
            logging.info(f"Starting processing: {gcs_uri}")

            start = time.perf_counter()
            doc = self.ai_client.process_blob(
                content=blob.download_as_bytes(),
                mime_type=MimeTypeResolver.get_mime_type(blob.name)
            )
            elapsed = time.perf_counter() - start
            logging.info(f"Processed {gcs_uri} in {elapsed:.2f}s")

            records = OCRExtractor.extract_records(gcs_uri, doc)
            self.exporter.write(records)

        self.exporter.close()
        logging.info(f"All text (with positions) has been written to {self.config.output_csv}")


if __name__ == '__main__':
    OCRPipeline(OCRConfig()).run()
