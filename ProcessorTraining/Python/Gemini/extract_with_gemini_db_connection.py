#!/usr/bin/env python3
import os
import io
import csv
import json
import fitz                                   # PyMuPDF
from google.cloud import storage, spanner
from google.oauth2 import service_account
from google.genai import Client, types
from clickhouse_driver import Client as CHClient

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PROJECT_ID   = "adg-delivery-moniepoint"     # ← must be the *ID*, not the number
LOCATION     = "us-central1"
BUCKET_NAME  = "adg-delivery-moniepoint-docs-bucket-001"
PREFIX       = "training-documents/"
OUTPUT_CSV   = "../Outputs/Gemini/gemini_entities.csv"
OUTPUT_JSON  = "../Outputs/Gemini/gemini_entities.json"
MODEL        = "gemini-2.0-flash-lite"

SA_KEY_PATH  = (
    "/home/adrian/PycharmProjects/"
    "KYC-document-pipeline/moniepoint-document-verification-service-playground/"
    "ProcessorTraining/.gcp/"
    "adg-documentai-sa-key.json"
)
SCOPES       = ["https://www.googleapis.com/auth/cloud-platform"]

# ─── CLICKHOUSE SETTINGS ─────────────────────────────────────────────────────
CH_HOST      = os.getenv("CH_HOST", "localhost")
CH_PORT      = int(os.getenv("CH_PORT", "9000"))
CH_USER      = os.getenv("CH_USER", "etl_writer")
CH_PASS      = os.getenv("CH_PASS", "a?xBVq1!")
CH_DB        = os.getenv("CH_DB", "utility_docs")
CH_TABLE     = "gemini_entities"

# ─── SPANNER SETTINGS ────────────────────────────────────────────────────────
SPANNER_INSTANCE = "doc-instance"
SPANNER_DATABASE = "utility_docs"
SPANNER_TABLE    = "gemini_entities"

# ─── INIT GCP & GENAI CLIENTS ────────────────────────────────────────────────
def init_clients():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY_PATH, scopes=SCOPES
    )
    storage_client = storage.Client(credentials=creds, project=PROJECT_ID)
    genai_client   = Client(
        vertexai=True,
        credentials=creds,
        project=PROJECT_ID,
        location=LOCATION,
    )
    return storage_client, genai_client, creds

# ─── INIT CLICKHOUSE & SPANNER ──────────────────────────────────────────────
def init_databases(creds):
    # -- ClickHouse TCP --
    try:
        ch = CHClient(
            host=CH_HOST,
            port=CH_PORT,
            user=CH_USER,
            password=CH_PASS,
            send_receive_timeout=30,
        )
        # idempotent DDL
        ch.execute(f"CREATE DATABASE IF NOT EXISTS {CH_DB}")
        ch.execute(f"""
            CREATE TABLE IF NOT EXISTS {CH_DB}.{CH_TABLE} (
              gcs_uri    String,
              page       UInt64,
              entity     String,
              value      String,
              confidence Float32
            ) ENGINE = MergeTree()
            ORDER BY (gcs_uri, page, entity)
        """)
        # switch into db
        ch = CHClient(
            host=CH_HOST,
            port=CH_PORT,
            user=CH_USER,
            password=CH_PASS,
            database=CH_DB,
            send_receive_timeout=30,
        )
        ch.execute("SELECT 1")
        print(f"✅ ClickHouse TCP OK @{CH_HOST}:{CH_PORT}")
        clickhouse_ready = True
    except Exception as e:
        print("⚠️ ClickHouse unavailable – skipping:", e)
        ch = None
        clickhouse_ready = False

    # -- Cloud Spanner --
    try:
        sp_client = spanner.Client(project=PROJECT_ID, credentials=creds)
        instance  = sp_client.instance(SPANNER_INSTANCE)
        db        = instance.database(SPANNER_DATABASE)

        # create table if missing
        create_tbl_ddl = f"""
          CREATE TABLE {SPANNER_TABLE} (
            gcs_uri    STRING(MAX)   NOT NULL,
            page       INT64,
            entity     STRING(MAX),
            value      STRING(MAX),
            confidence FLOAT64
          ) PRIMARY KEY (gcs_uri, page, entity)
        """
        op = db.update_ddl([create_tbl_ddl])
        op.result()  # wait for it
        print(f"✅ Spanner table ensured @ {SPANNER_DATABASE}/{SPANNER_TABLE}")
        spanner_ready = True
    except Exception as e:
        print("⚠️ Spanner unavailable or no permission – skipping:", e)
        db = None
        spanner_ready = False

    return ch, clickhouse_ready, db, spanner_ready

# ─── PDF→PNG ─────────────────────────────────────────────────────────────────
def pdf_to_images(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        pages.append(pix.tobytes("png"))
    return pages

# ─── CALL GEMINI ─────────────────────────────────────────────────────────────
def call_gemini(genai_client, image_bytes):
    prompt = (
        "You are a document‐understanding assistant.\n"
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
        "The output must be a valid JSON array object listing all the extracted values."
    )
    parts = [
        types.Part.from_text(text=prompt),
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
    ]
    resp = genai_client.models.generate_content(
        model=MODEL,
        contents=parts,
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=1024),
    )
    raw = resp.text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()[1:-1]
        raw   = "\n".join(lines)
    return json.loads(raw)

# ─── PROCESS ONE BLOB ────────────────────────────────────────────────────────
def process_blob(blob, genai_client):
    data = blob.download_as_bytes()
    ext  = os.path.splitext(blob.name)[1].lower()
    pages = pdf_to_images(data) if ext == ".pdf" else [data]
    out = []
    for i, img in enumerate(pages, start=1):
        try:
            ents = call_gemini(genai_client, img)
        except Exception as e:
            print(f"  ! error on page {i}: {e}")
            continue
        for e in ents:
            e["page"] = i
        out.extend(ents)
    return out

# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    # make sure output path exists
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    storage_client, genai_client, creds = init_clients()
    ch, ch_ok, db, sp_ok              = init_databases(creds)

    '''JSONL output file'''
    json_fh = open(OUTPUT_JSON, "w", encoding="utf-8")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["gcs_uri","page","entity","value","confidence"],
        )
        writer.writeheader()

        for blob in storage_client.list_blobs(BUCKET_NAME, prefix=PREFIX):
            if blob.name.endswith("/") or not blob.name.lower().endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
            ):
                continue

            uri  = f"gs://{BUCKET_NAME}/{blob.name}"
            print("→", uri)
            ents = process_blob(blob, genai_client)

            for e in ents:
                row = {
                    "gcs_uri":    uri,
                    "page":       int(e.get("page", 0)),
                    "entity":     e.get("entity", ""),
                    "value":      e.get("value", ""),
                    "confidence": float(e.get("confidence", 0.0)),
                }
                writer.writerow(row)
                '''JSON Write row to JSONL'''
                json_line = json.dumps(row, ensure_ascii=False)
                json_fh.write(json_line + "\n")

                obj = json.loads(json_line)

                # ClickHouse insert
                if ch_ok:
                    try:
                        ch.execute(
                            f"INSERT INTO {CH_TABLE} (gcs_uri,page,entity,value,confidence) VALUES",
                            [(row["gcs_uri"], row["page"], row["entity"], row["value"], row["confidence"])],
                        )
                    except Exception as ex:
                        print("  ⚠️ CH write failed:", ex)

                # Spanner insert
                if sp_ok:
                    def txn_write(txn):
                        txn.insert(
                            table   = SPANNER_TABLE,
                            columns = ["gcs_uri","page","entity","value","confidence"],
                            values  = [(
                                obj["gcs_uri"],
                                obj["page"],
                                obj["entity"],
                                obj["value"],
                                obj["confidence"],
                            )],
                        )
                    try:
                        db.run_in_transaction(txn_write)
                    except Exception as ex:
                        print("  ⚠️ Spanner write failed:", ex)


    json_fh.close()
    print(f"Done! Results → {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
