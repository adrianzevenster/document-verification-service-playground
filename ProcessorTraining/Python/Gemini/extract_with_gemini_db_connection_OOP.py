import os
import io
import csv
import json
import fitz  # PyMuPDF
from google.cloud import storage, spanner
from google.oauth2 import service_account
from google.genai import Client, types
from clickhouse_driver import Client as CHClient


class Config:
    PROJECT_ID = "adg-delivery-moniepoint"  # must be the ID, not the number
    LOCATION = "us-central1"
    BUCKET_NAME = "adg-delivery-moniepoint-docs-bucket-001"
    PREFIX = "training-documents/"
    OUTPUT_CSV = "../Outputs/Gemini/gemini_entities.csv"
    OUTPUT_JSON = "../Outputs/Gemini/gemini_entities.json"
    MODEL = "gemini-2.0-flash-lite"

    SA_KEY_PATH = (
        "/home/adrian/PycharmProjects/"
        "KYC-document-pipeline/moniepoint-document-verification-service-playground/"
        "ProcessorTraining/.gcp/"
        "adg-documentai-sa-key.json"
    )
    SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

    # ClickHouse settings
    CH_HOST = os.getenv("CH_HOST", "localhost")
    CH_PORT = int(os.getenv("CH_PORT", "9000"))
    CH_USER = os.getenv("CH_USER", "etl_writer")
    CH_PASS = os.getenv("CH_PASS", "a?xBVq1!")
    CH_DB = os.getenv("CH_DB", "utility_docs")
    CH_TABLE = "gemini_entities"

    # Spanner settings
    SPANNER_INSTANCE = "doc-instance"
    SPANNER_DATABASE = "utility_docs"
    SPANNER_TABLE = "gemini_entities"


class ClientManager:
    @staticmethod
    def init_clients():
        creds = service_account.Credentials.from_service_account_file(
            Config.SA_KEY_PATH, scopes=Config.SCOPES
        )
        storage_client = storage.Client(
            credentials=creds, project=Config.PROJECT_ID
        )
        genai_client = Client(
            vertexai=True,
            credentials=creds,
            project=Config.PROJECT_ID,
            location=Config.LOCATION,
        )
        return storage_client, genai_client, creds


class DatabaseManager:
    def __init__(self, creds):
        self.creds = creds
        self.ch = None
        self.spanner_db = None
        self.ch_ok = False
        self.sp_ok = False
        self._init_clickhouse()
        self._init_spanner()

    def _init_clickhouse(self):
        try:
            client = CHClient(
                host=Config.CH_HOST,
                port=Config.CH_PORT,
                user=Config.CH_USER,
                password=Config.CH_PASS,
                send_receive_timeout=30,
            )
            client.execute(f"CREATE DATABASE IF NOT EXISTS {Config.CH_DB}")
            client.execute(f"""
                CREATE TABLE IF NOT EXISTS {Config.CH_DB}.{Config.CH_TABLE} (
                  gcs_uri    String,
                  page       UInt64,
                  entity     String,
                  value      String,
                  confidence Float32
                ) ENGINE = MergeTree()
                ORDER BY (gcs_uri, page, entity)
            """)
            self.ch = CHClient(
                host=Config.CH_HOST,
                port=Config.CH_PORT,
                user=Config.CH_USER,
                password=Config.CH_PASS,
                database=Config.CH_DB,
                send_receive_timeout=30,
            )
            self.ch.execute("SELECT 1")
            print(f"✅ ClickHouse TCP OK @{Config.CH_HOST}:{Config.CH_PORT}")
            self.ch_ok = True
        except Exception as e:
            print("⚠️ ClickHouse unavailable – skipping:", e)

    def _init_spanner(self):
        try:
            sp_client = spanner.Client(
                project=Config.PROJECT_ID, credentials=self.creds
            )
            instance = sp_client.instance(Config.SPANNER_INSTANCE)
            db = instance.database(Config.SPANNER_DATABASE)
            ddl = f"""
              CREATE TABLE {Config.SPANNER_TABLE} (
                gcs_uri    STRING(MAX)   NOT NULL,
                page       INT64,
                entity     STRING(MAX),
                value      STRING(MAX),
                confidence FLOAT64
              ) PRIMARY KEY (gcs_uri, page, entity)
            """
            op = db.update_ddl([ddl])
            op.result()
            self.spanner_db = db
            print(f"✅ Spanner table ensured @ {Config.SPANNER_DATABASE}/{Config.SPANNER_TABLE}")
            self.sp_ok = True
        except Exception as e:
            print("⚠️ Spanner unavailable or no permission – skipping:", e)


class PDFConverter:
    @staticmethod
    def pdf_to_images(pdf_bytes):
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            images.append(pix.tobytes("png"))
        return images


class GeminiExtractor:
    def __init__(self, genai_client):
        self.client = genai_client
        self.model = Config.MODEL

    def call(self, image_bytes):
        prompt = (
            "You are a document-understanding assistant.\n"
            "Extract the following fields and output ONLY a JSON array of objects:\n"
            "- Supply Address\n"
            "- Service Address\n"
            "- Customer Name\n"
            "- Period\n"
            "- Meter Number\n"
            "- Meter #\n"
            "- Meter Type\n"
            "- Transaction Date\n"
            "- Address\n"
            "- Bill Month\n"
            "- Customer Account\n"
            "- providerAcronym\n\n"
            "Each object must have:\n"
            "  \"entity\": field name,\n"
            "  \"value\": extracted text,\n"
            "  \"confidence\": float between 0.0 and 1.0\n\n"
            "If a field is missing, omit it. DO NOT output any extra text."
        )
        parts = [
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ]
        resp = self.client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=1024),
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()[1:-1]
            raw = "\n".join(lines)
        return json.loads(raw)


class BlobProcessor:
    def __init__(self, extractor):
        self.extractor = extractor

    def process(self, blob):
        data = blob.download_as_bytes()
        ext = os.path.splitext(blob.name)[1].lower()
        pages = (
            PDFConverter.pdf_to_images(data) if ext == ".pdf" else [data]
        )
        results = []
        for idx, img in enumerate(pages, start=1):
            try:
                ents = self.extractor.call(img)
            except Exception as e:
                print(f"  ! error on page {idx}: {e}")
                continue
            for ent in ents:
                ent["page"] = idx
            results.extend(ents)
        return results


class DataWriter:
    def __init__(self, csv_path, json_path, db_manager):
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self.csv_fh = open(csv_path, "w", newline="", encoding="utf-8")
        self.json_fh = open(json_path, "w", encoding="utf-8")
        self.writer = csv.DictWriter(
            self.csv_fh,
            fieldnames=["gcs_uri", "page", "entity", "value", "confidence"],
        )
        self.writer.writeheader()
        self.db_manager = db_manager

    def write(self, row):
        self.writer.writerow(row)
        json_line = json.dumps(row, ensure_ascii=False)
        self.json_fh.write(json_line + "\n")

        # ClickHouse insert
        if self.db_manager.ch_ok:
            try:
                self.db_manager.ch.execute(
                    f"INSERT INTO {Config.CH_TABLE} (gcs_uri, page, entity, value, confidence) VALUES",  # noqa
                    [(row["gcs_uri"], row["page"], row["entity"], row["value"], row["confidence"])],
                )
            except Exception as e:
                print("  ⚠️ CH write failed:", e)

        # Spanner insert
        if self.db_manager.sp_ok:
            def _txn(txn):
                txn.insert(
                    table=Config.SPANNER_TABLE,
                    columns=["gcs_uri", "page", "entity", "value", "confidence"],
                    values=[(
                        row["gcs_uri"],
                        row["page"],
                        row["entity"],
                        row["value"],
                        row["confidence"],
                    )],
                )
            try:
                self.db_manager.spanner_db.run_in_transaction(_txn)
            except Exception as e:
                print("  ⚠️ Spanner write failed:", e)

    def close(self):
        self.csv_fh.close()
        self.json_fh.close()


class Processor:
    def __init__(self):
        self.storage_client, genai_client, creds = ClientManager.init_clients()
        self.db_manager = DatabaseManager(creds)
        self.extractor = GeminiExtractor(genai_client)
        self.blob_processor = BlobProcessor(self.extractor)
        self.writer = DataWriter(
            Config.OUTPUT_CSV, Config.OUTPUT_JSON, self.db_manager
        )

    def run(self):
        for blob in self.storage_client.list_blobs(
                Config.BUCKET_NAME, prefix=Config.PREFIX
        ):
            if blob.name.endswith("/") or not blob.name.lower().endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
            ):
                continue
            uri = f"gs://{Config.BUCKET_NAME}/{blob.name}"
            print("→", uri)
            entities = self.blob_processor.process(blob)
            for ent in entities:
                row = {
                    "gcs_uri": uri,
                    "page": int(ent.get("page", 0)),
                    "entity": ent.get("entity", ""),
                    "value": ent.get("value", ""),
                    "confidence": float(ent.get("confidence", 0.0)),
                }
                self.writer.write(row)
        self.writer.close()
        print(f"Done! Results → {Config.OUTPUT_CSV}")


if __name__ == "__main__":
    Processor().run()
