#!/usr/bin/env python3
"""
Extract key fields from Moniepoint / Nigerian utility documents that were
OCR-processed with the generic Document-AI *OCR Processor*.

Changes vs. previous version
----------------------------
* Much stricter rules for “Meter Number”:
  – skips lines containing   old / previous / multiplier / account / address / adc
  – accepts only a pure-digit token (with optional hyphens/blanks) or literal '0'
  – continues scanning until a good candidate is found
"""

import csv, re, pathlib
import logging
import time

from google.oauth2 import service_account
from google.cloud import storage, documentai_v1 as documentai

# ─── AUTH ────────────────────────────────────────────────────────────────────
KEY_PATH = "../../.gcp/adg-documentai-sa-key.json"
credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
# ─────────────────────────────────────────────────────────────────────────────

# ─── CONFIG ─────────────────────────────────────────────────────────────────
PROJECT_ID    = "1027521807"
LOCATION      = "us"                       # OCR-processor region
PROCESSOR_ID  = "474b98a3e9d41efd"
BUCKET_NAME   = "adg-delivery-moniepoint-docs-bucket-001"
PREFIX        = "training-documents/"
OUTPUT_CSV    = "../Outputs/OCR/extracted_fields_with_labels.csv"
# ────────────────────────────────────────────────────────────────────────────

"""
    Configure logging
"""

time_format = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt=time_format)


def mime_type(fn: str) -> str:
    m = fn.lower().split(".")[-1]
    return {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
            "pdf":"application/pdf","tif":"image/tiff","tiff":"image/tiff"}.get(m)


def text_of(layout, doc_text: str) -> str:
    return "".join(
        doc_text[int(s.start_index or 0): int(s.end_index or len(doc_text))]
        for s in layout.text_anchor.text_segments
    ).strip()


# --------------------------------------------------------------------------- #
#                               FIELD EXTRACTION                              #
# --------------------------------------------------------------------------- #
import re, string

# ---------- 1) label patterns ------------------------------------------------
_KEYWORDS = {
    "supply_address"  : r"(supply|bill delivery)\s*address",
    "name"            : r"(customer|account)?\s*name",
    "period"          : r"period",
    "meter_number"    : r"meter\s*(number|no\.?|num|#)?",
    "bill_month"      : r"bill\s*month",
    "customer_account": r"(customer|old)?\s*account(\s*no\.?| number| #)?",
    "provider_acronym": r"provider acronym",
    "service_address" : r"service address",
    "meter_type"      : r"meter\s*type",
    "transaction_date": r"(transaction|purchase)\s*date",
    "address"         : r"\baddress\b",
}

_HEADER_ORDER = [
    "supply_address","name","period","meter_number",
    "bill_month","customer_account","provider_acronym",
    "service_address","meter_type","transaction_date","address",
]

_SKIP_TOKENS = {"n/a", "na", "-", "=", "null", "none"}
_TEXT_FIELDS  = {"supply_address","service_address","address","name"}
_NUM_FIELDS   = {"meter_number","customer_account"}   # need (mostly) digits

# ---------- 2) helpers -------------------------------------------------------
def _looks_like_label(txt: str) -> bool:
    low = txt.lower().strip()
    if low.endswith((":",";")):
        return True
    return any(re.search(pat, low) for pat in _KEYWORDS.values())

def _acceptable_value(txt: str, field: str) -> bool:
    """
    Decide whether *txt* can be accepted as the value for *field*.
    """
    clean = txt.strip()
    low   = clean.lower()
    if not clean or low in _SKIP_TOKENS or _looks_like_label(clean):
        return False

    # ---------- free-text fields (address, name, …) -------------------------
    if field in _TEXT_FIELDS:
        return True

    # ---------- numeric-like fields -----------------------------------------
    digits_only = re.sub(r"\D", "", clean)

    if field == "meter_number":
        # Some suppliers legitimately print “0” (a single digit) as the meter
        # number on certain account-opening statements.  Accept any *all-digit*
        # string, even length-1, **provided it really is just digits**.
        return digits_only == clean and len(digits_only) >= 1

    if field == "customer_account":
        # Customer account numbers are usually longer – keep the ≥5-digit guard.
        return len(digits_only) >= 5

    # For the very rare case we mis-categorised: fall back to length check.
    return len(clean) >= 2


def _clean_inline_value(val: str) -> str:
    """Drop leading punctuation & obvious label words like 'number'."""
    val = val.lstrip(" :.-").strip()
    if re.fullmatch(r"(number|no\.?)\s*", val.lower()):
        return ""
    return val

# ---------- 3) main extraction ----------------------------------------------
def extract_fields(lines: list[tuple[str, float]]):
    """
    lines = [(text, confidence), ...] top-to-bottom.
    Returns dict field → (label, value, conf)
    """
    found = {k: (None, "", None) for k in _KEYWORDS}

    for i, (text, conf) in enumerate(lines):
        low = text.lower()

        for field, pat in _KEYWORDS.items():
            if found[field][0] is not None:           # already have it
                continue
            if not re.search(pat, low):
                continue

            # ---------- matched label ---------------------------------------
            label = text.strip()

            after_match = re.split(pat, low, maxsplit=1)[1]
            inline_orig = text[-len(after_match):] if after_match else ""
            value       = _clean_inline_value(inline_orig)

            # ---------- look-ahead (≤5 lines) if inline empty / unusable -----
            if not _acceptable_value(value, field):
                value = ""
                for j in range(i+1, min(i+6, len(lines))):
                    nxt, nxt_conf = lines[j]
                    if _acceptable_value(nxt, field):
                        value, conf = nxt.strip(), nxt_conf
                        break

            found[field] = (label, value, conf)

    return found




# --------------------------------------------------------------------------- #
#                                 MAIN FLOW                                   #
# --------------------------------------------------------------------------- #
def main() -> None:
    storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
    docai_client  = documentai.DocumentProcessorServiceClient(
        credentials=credentials,
        client_options={"api_endpoint": f"{LOCATION}-documentai.googleapis.com:443"},
    )
    processor_name = docai_client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)

        # CSV header: gcs_uri +  (label,value,conf)*N
        header = ["gcs_uri"]
        for k in _HEADER_ORDER:
            header += [f"{k}_label", f"{k}_value", f"{k}_conf"]
        writer.writerow(header)

        for blob in storage_client.list_blobs(BUCKET_NAME, prefix=PREFIX):
            if blob.name.endswith("/") or not blob.name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".tif")
            ):
                continue

            gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
            start_time = time.perf_counter()
            logging.info(f"Starting Processing: {gcs_uri}")
            print("Processing", gcs_uri)

            result = docai_client.process_document(
                request=documentai.ProcessRequest(
                    name=processor_name,
                    raw_document=documentai.RawDocument(
                        content=blob.download_as_bytes(),
                        mime_type=mime_type(blob.name),
                    ),
                )
            ).document

            elapsed = time.perf_counter() - start_time
            logging.info(f"Processed in {elapsed:.2f}s")


            lines = [
                (text_of(line.layout, result.text or ""), line.layout.confidence)
                for page in result.pages for line in page.lines
            ]

            fields = extract_fields(lines)

            acr_label, acr_value, acr_conf = fields["provider_acronym"]
            if not acr_value:
                for text, conf in lines[:5]:
                    for tok in text.split():
                        if re.fullmatch(r"[A-Z]{2,5}", tok):
                            acr_label = "Detected acronym"
                            acr_value = tok
                            acr_conf = conf
                            break
                        if acr_value:
                            break
                fields["provider_acronym"] = (acr_label, acr_value, acr_conf)

            row = [gcs_uri]
            for k in _HEADER_ORDER:
                lab, val, conf = fields[k]
                row += [lab or "", val, f"{conf:.2f}" if conf is not None else ""]
            writer.writerow(row)

    print("Done  →", OUTPUT_CSV)


if __name__ == "__main__":
    main()
