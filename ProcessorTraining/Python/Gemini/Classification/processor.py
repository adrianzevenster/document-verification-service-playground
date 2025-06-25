from __future__ import annotations

import json
from google.cloud import storage

from .config            import Config
from .client_manager     import init_clients
from .database_manager   import DatabaseManager
from .gemini_extractor   import GeminiExtractor
from .gemini_classifier  import GeminiClassifier
from .blob_processor     import BlobProcessor
from .data_writer        import DataWriter
from .metadata_extraction_service import MetadataExtractor


class Processor:
    """Drives: GCS → Gemini classify/extract → metadata → CSV/JSON (±DB)."""

    def __init__(self) -> None:
        # ───────────────────────────── infra clients ───────────────────────────
        self.storage_client, genai_client, creds = init_clients()
        self.db            = DatabaseManager(creds)

        # ────────────────────────── Gemini helpers ─────────────────────────────
        self.extractor   = GeminiExtractor(genai_client)
        self.classifier  = GeminiClassifier(genai_client)
        self.blob_proc   = BlobProcessor(self.extractor, self.classifier)

        # ───────────────────────────── writers ─────────────────────────────────
        self.ent_writer  = DataWriter(Config.ENT_CSV,  Config.ENT_JSON,  self.db)
        self.cls_writer  = DataWriter(Config.CLS_CSV,  Config.CLS_JSON,  self.db)
        self.meta_writer = DataWriter(Config.META_CSV, Config.META_JSON, self.db)

        self.meta_extract = MetadataExtractor()

    # ──────────────────────────────────────────────────────────────────────────
    def run(self) -> None:
        blobs = self.storage_client.list_blobs(
            Config.BUCKET_NAME, prefix=Config.PREFIX
        )

        for blob in blobs:
            if blob.name.endswith("/") or not blob.name.lower().endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
            ):
                continue

            uri = f"gs://{Config.BUCKET_NAME}/{blob.name}"
            print("→", uri)

            # 1️⃣  Gemini classification & entities
            doc_type, ents = self.blob_proc.process(blob)

            # single classifier row
            self.cls_writer.write({
                "gcs_uri": uri,
                "page": 0,
                "document_type": doc_type,
                "entity": "",
                "value": "",
                "confidence": 0.0,
            })

            # entity rows
            for ent in ents:
                self.ent_writer.write({
                    "gcs_uri":       uri,
                    "page":          int(ent.get("page", 0)),
                    "document_type": doc_type,
                    "entity":        ent.get("entity", ""),
                    "value":         ent.get("value", ""),
                    "confidence":    float(ent.get("confidence", 0.0)),
                })

            # 2️⃣  Metadata rows (file & GCS)
            meta = self.meta_extract.extract(
                blob.download_as_bytes(), filename=blob.name, mime_type=blob.content_type
            )
            # add GCS timestamps
            meta["gcs.updated"] = blob.updated.isoformat() if blob.updated else ""
            meta["gcs.time_created"] = (
                blob.time_created.isoformat() if blob.time_created else ""
            )

            for k, v in meta.items():
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)

                self.meta_writer.write({
                    "gcs_uri": uri,
                    "page": 0,
                    "document_type": doc_type,
                    "entity": f"meta:{k}",
                    "value": v,
                    "confidence": 1.0,
                })

        # flush all writers
        self.ent_writer.close()
        self.cls_writer.close()
        self.meta_writer.close()
        print(
            "✓ Done – outputs:" \
            f"\n   • {Config.CLS_CSV}\n   • {Config.ENT_CSV}\n   • {Config.META_CSV}"
        )


if __name__ == "__main__":
    Processor().run()
