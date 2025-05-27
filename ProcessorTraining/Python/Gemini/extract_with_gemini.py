#!/usr/bin/env python3
import os
import csv
import json
import fitz                                   # PyMuPDF
from google.cloud import storage
from google.oauth2 import service_account
from google.genai import Client, types

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PROJECT_ID   = "1027521807"
LOCATION     = "us-central1"
BUCKET_NAME  = "adg-delivery-moniepoint-docs-bucket-001"
PREFIX       = "training-documents/"
OUTPUT_CSV   = "../Outputs/Gemini/gemini_entities.csv"
MODEL        = "gemini-2.0-flash-lite"

# Path to your service-account JSON, and the OAuth scope required
SA_KEY_PATH  = (
    "/home/adrian/PycharmProjects/"
    "KYC-document-pipeline/moniepoint-document-verification-service-playground/"
    "ProcessorTraining/.gcp/"
    "adg-documentai-sa-key.json"
)
SCOPES       = ["https://www.googleapis.com/auth/cloud-platform"]
# ──────────────────────────────────────────────────────────────────────────────

def init_clients():
    # Load the service account key with the full cloud-platform scope
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY_PATH,
        scopes=SCOPES,
    )

    # Storage client
    storage_client = storage.Client(
        credentials=creds,
        project=PROJECT_ID,
    )

    # GenAI (Vertex AI) client
    genai_client = Client(
        vertexai=True,
        credentials=creds,
        project=PROJECT_ID,
        location=LOCATION,
    )

    return storage_client, genai_client


def pdf_to_images(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        pages.append(pix.tobytes("png"))
    return pages


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
        '  \"entity\": field name,\n'
        '  \"value\": extracted text,\n'
        '  \"confidence\": float between 0.0 and 1.0\n\n'
        "If a field is missing, omit it. DO NOT output any extra text."
    )

    parts = [
        types.Part.from_text(text=prompt),
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
    ]

    response = genai_client.models.generate_content(
        model=MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )

    # Get the raw text; strip code fences if present
    raw = response.text
    raw_str = raw.strip()
    if raw_str.startswith("```"):
        lines = raw_str.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("⚠️  Failed to parse JSON. Raw output:\n", raw)
        raise


def process_blob(blob, genai_client):
    data = blob.download_as_bytes()
    ext  = os.path.splitext(blob.name)[1].lower()

    if ext == ".pdf":
        pages = pdf_to_images(data)
    elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        pages = [data]
    else:
        return []

    all_entities = []
    for i, img in enumerate(pages, start=1):
        try:
            ents = call_gemini(genai_client, img)
        except Exception as e:
            print(f"  ! error on page {i}: {e}")
            continue
        for ent in ents:
            ent["page"] = i
        all_entities.extend(ents)

    return all_entities


def main():
    storage_client, genai_client = init_clients()
    blobs = storage_client.list_blobs(BUCKET_NAME, prefix=PREFIX)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["gcs_uri", "page", "entity", "value", "confidence"],
        )
        writer.writeheader()

        for blob in blobs:
            if blob.name.endswith("/") or not blob.name.lower().endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
            ):
                continue

            print("→", blob.name)
            uri = f"gs://{BUCKET_NAME}/{blob.name}"
            ents = process_blob(blob, genai_client)

            for e in ents:
                writer.writerow({
                    "gcs_uri":    uri,
                    "page":       e.get("page"),
                    "entity":     e.get("entity"),
                    "value":      e.get("value"),
                    "confidence": e.get("confidence"),
                })

    print(f"Done! Results written to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
