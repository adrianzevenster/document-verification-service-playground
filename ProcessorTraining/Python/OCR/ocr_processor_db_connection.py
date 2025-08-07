#!/usr/bin/env python3
"""
Extract key fields via Document AI OCR, then write to:
 • CSV
 • Cloud Spanner
 • ClickHouse (native TCP)
"""

import os, io, csv, re, sys
from google.oauth2 import service_account
from google.cloud import storage, documentai_v1 as documentai
from google.cloud import spanner as _spanner
from clickhouse_driver import Client as _CHClient
import json

# ─── AUTH & CONFIG ─────────────────────────────────────────────────────────
KEY_PATH  = "/home/adrian/PycharmProjects/KYC-document-pipeline/moniepoint-document-verification-service/ProcessorTraining/.gcp/adg-documentai-sa-key.json"
credentials = service_account.Credentials.from_service_account_file(KEY_PATH)

PROJECT_ID   = "1027521807"
LOCATION     = "us"
PROCESSOR_ID = "474b98a3e9d41efd"
BUCKET_NAME  = "adg-delivery-moniepoint-docs-bucket-001"
PREFIX       = "training-documents/"
OUTPUT_CSV   = "extracted_fields_with_labels.csv"

# ─── THE FIELDS YOU WANT TO EXTRACT ────────────────────────────────────────
FIELDS = [
    "supply_address",
    "name",
    "period",
    "meter_number",
    "bill_month",
    "customer_account",
    "provider_acronym",
    "service_address",
    "meter_type",
    "transaction_date",
    "address",
]

_KEYWORDS = {
    "supply_address":   r"(supply|bill delivery)\s*address",
    "name":             r"(customer|account)?\s*name",
    "period":           r"period",
    "meter_number":     r"meter\s*(number|no\.?|num|#)?",
    "bill_month":       r"bill\s*month",
    "customer_account": r"(customer|old)?\s*account(\s*no\.?| number| #)?",
    "provider_acronym": r"provider acronym",
    "service_address":  r"service address",
    "meter_type":       r"meter\s*type",
    "transaction_date": r"(transaction|purchase)\s*date",
    "address":          r"\baddress\b",
}

# ─── CLICKHOUSE TCP SETTINGS ───────────────────────────────────────────────
CLICKHOUSE_HOST  = os.getenv("CH_HOST", "localhost")
CLICKHOUSE_PORT  = int(os.getenv("CH_PORT", 9000))
CLICKHOUSE_DB    = os.getenv("CH_DB", "utility_docs")
CLICKHOUSE_USER  = os.getenv("CH_USER", "etl_writer")
CLICKHOUSE_PASS  = os.getenv("CH_PASS", "a?xBVq1!")
CLICKHOUSE_TABLE = "extracted_fields"

# ─── CLOUD SPANNER SETTINGS ────────────────────────────────────────────────
SPANNER_INSTANCE = "doc-instance"
SPANNER_DATABASE = "utility_docs"
SPANNER_TABLE    = "extracted_fields"

# ─── BUILD CSV HEADER ───────────────────────────────────────────────────────
CSV_HEADER = ["gcs_uri"]
for f in FIELDS:
    CSV_HEADER += [f + "_label", f + "_value", f + "_conf"]

# ─── BUILD CLICKHOUSE DDL ──────────────────────────────────────────────────
def clickhouse_ddl():
    cols = ["gcs_uri String"]
    for f in FIELDS:
        cols += [
            f + "_label String",
            f + "_value String",
            f + "_conf Float32",
            ]
    body = ",\n  ".join(cols)
    return [
        f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}",
        f"""
        CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE}
        (
          {body}
        )
        ENGINE = MergeTree()
        ORDER BY gcs_uri
        """.strip(),
    ]

# ─── CLICKHOUSE TCP CLIENT INIT ────────────────────────────────────────────
try:
    ch = _CHClient(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASS,
        send_receive_timeout=30,
    )
    for stmt in clickhouse_ddl():
        try:
            ch.execute(stmt)
        except Exception:
            pass
    ch = _CHClient(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASS,
        database=CLICKHOUSE_DB,
        send_receive_timeout=30,
    )
    ch.execute("SELECT 1")
    CLICKHOUSE_READY = True
    print(f"✅ ClickHouse TCP OK @{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}")
except Exception as e:
    CLICKHOUSE_READY = False
    print("⚠️ ClickHouse unavailable – skipping:", e)

# ─── CLICKHOUSE WRITE HELPER ─────────────────────────────────────────────────
def _write_clickhouse(row):
    if not CLICKHOUSE_READY:
        return
    # coerce conf columns to float, leave others as-is
    typed = []
    total_cols = 1 + len(FIELDS)*3
    if len(row) != total_cols:
        print(f"❌ internal error: expected {total_cols} columns for ClickHouse, got {len(row)}")
        return
    for i, v in enumerate(row):
        # gcs_uri or label/value columns
        if i == 0 or (i-1) % 3 != 2:
            typed.append(v)
        else:
            try:
                typed.append(float(v))
            except:
                typed.append(0.0)
    # insert as a single-row batch
    ch.execute(
        f"INSERT INTO {CLICKHOUSE_TABLE} VALUES",
        [tuple(typed)]
    )

# ─── SPANNER INITIALIZATION (NO DDL) ────────────────────────────────────────
# Make sure we point at the same project ID you granted IAM on
SPANNER_PROJECT = os.getenv("SPANNER_PROJECT", "adg-delivery-moniepoint")
sp_client       = _spanner.Client(
    project=SPANNER_PROJECT,
    credentials=credentials,
)
# Database handle for inserts
global sp_db
sp_db = sp_client.instance(SPANNER_INSTANCE).database(SPANNER_DATABASE)

def _ensure_spanner_db_and_table():
    # no-op: schema is managed externally
    return

# ─── SPANNER INSERT UTILITY ─────────────────────────────────────────────────
SPANNER_COLUMNS = ["gcs_uri"] + [
    col for f in FIELDS for col in (f + "_label", f + "_value", f + "_conf")
]

def _write_spanner(row):
    values = []
    for idx, v in enumerate(row):
        if idx == 0 or (idx-1) % 3 != 2:
            values.append(v)
        else:
            try:
                values.append(float(v))
            except:
                values.append(None)
    def txn_insert(txn):
        txn.insert(
            table=SPANNER_TABLE,
            columns=SPANNER_COLUMNS,
            values=[tuple(values)]
        )
    try:
        sp_db.run_in_transaction(txn_insert)
        print(f"✅ Spanner write OK for {values[0]}")
    except Exception as e:
        print("⚠️ Spanner write failed:", e)

# ─── EXTRACTION HELPERS ─────────────────────────────────────────────────────
def _looks_like_label(txt):
    low = txt.lower().strip()
    return low.endswith((":",";")) or any(re.search(p, low) for p in _KEYWORDS.values())

def _acceptable_value(txt, field):
    c = txt.strip()
    if not c or c.lower() in {"n/a","na","-","=","null","none"} or _looks_like_label(c):
        return False
    if field in {"supply_address","service_address","address","name"}:
        return True
    digits = re.sub(r"\D","",c)
    if field == "meter_number":
        return digits == c and len(digits) >= 1
    if field == "customer_account":
        return len(digits) >= 5
    return len(c) >= 2

def _clean_inline_value(val):
    v = val.lstrip(" :.-").strip()
    if re.fullmatch(r"(number|no\.?)\s*", v.lower()):
        return ""
    return v

def extract_fields(lines):
    found = {f:(None,"",None) for f in FIELDS}
    for idx,(text,conf) in enumerate(lines):
        low = text.lower()
        for field,pat in _KEYWORDS.items():
            if found[field][0] or not re.search(pat, low):
                continue
            label = text.strip()
            rest = re.split(pat, low,1)[1]
            inline = text[-len(rest):] if rest else ""
            val = _clean_inline_value(inline)
            if not _acceptable_value(val, field):
                val = ""
                for j in range(idx+1, min(idx+6,len(lines))):
                    nxt, c2 = lines[j]
                    if _acceptable_value(nxt, field):
                        val,conf = nxt.strip(),c2
                        break
            found[field] = (label,val,conf)
    return found

def mime_type(fn):
    ext = fn.lower().split('.')[-1]
    return {
        "png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
        "pdf":"application/pdf","tif":"image/tiff","tiff":"image/tiff",
    }.get(ext)

def text_of(layout, txt):
    return "".join(
        txt[int(s.start_index or 0):int(s.end_index or len(txt))]
        for s in layout.text_anchor.text_segments
    ).strip()

# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    _ensure_spanner_db_and_table()

    json_fh = open(OUTPUT_CSV, "w", encoding="utf-8")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)

        storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
        docai_client   = documentai.DocumentProcessorServiceClient(
            credentials=credentials,
            client_options={"api_endpoint": f"{LOCATION}-documentai.googleapis.com:443"},
        )
        proc_name = docai_client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

        for blob in storage_client.list_blobs(BUCKET_NAME, prefix=PREFIX):
            if not blob.name.lower().endswith((".png",".jpg",".jpeg",".pdf",".tif",".tiff")):
                continue
            gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
            print("Processing", gcs_uri)

            res = docai_client.process_document(
                request=documentai.ProcessRequest(
                    name=proc_name,
                    raw_document=documentai.RawDocument(
                        content=blob.download_as_bytes(),
                        mime_type=mime_type(blob.name),
                    ),
                )
            ).document

            lines = [
                (text_of(line.layout, res.text or ""), line.layout.confidence)
                for page in res.pages for line in page.lines
            ]
            fields = extract_fields(lines)

            row = [gcs_uri]
            for f in FIELDS:
                lab,val,conf = fields[f]
                row += [lab or "", val, f"{conf:.2f}" if conf is not None else ""]

            if len(row) != len(CSV_HEADER):
                print(f"❌ internal error: row has {len(row)} cols, expected {len(CSV_HEADER)}")
                sys.exit(1)

            writer.writerow(row)
            _write_clickhouse(row)
            _write_spanner(row)

            obj = {"gcs_uri": gcs_uri}
            for f in FIELDS:
                lab, val, conf = fields[f]
                obj[f] = {
                    "label": lab or "",
                    "value": val,
                    "confidence": conf if conf is not None else None
                }
            json_fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            print(obj)

    print("Done →", OUTPUT_CSV)

if __name__ == "__main__":
    main()
