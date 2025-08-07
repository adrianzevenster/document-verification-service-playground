import os
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Config:
    # ────────────────────────────── Vertex AI ───────────────────────────
    PROJECT_ID:   str = "adg-delivery-moniepoint"
    LOCATION:     str = "us-central1"
    MODEL:        str = "gemini-2.0-flash-lite"     # base (entities)
    TUNED_MODEL:  str = os.getenv("TUNED_GEMINI_MODEL", MODEL)  # classifier

    # ─────────────────────────── Data sources ───────────────────────────
    BUCKET_NAME:  str = "adg-delivery-moniepoint-docs-bucket-001"
    PREFIX:       str = "training-documents"

    # ─────────────────────── ENTITY-EXTRACTION sinks ────────────────────
    ENT_JSON:  str = "../Outputs/Gemini/gemini_entities.jsonl"
    ENT_CSV:   str = "../Outputs/Gemini/gemini_entities.csv"
    ENT_TABLE: str = "gemini_entities"             # ClickHouse + Spanner

    # ───────────── DOCUMENT-TYPE CLASSIFIER sinks ────────────────
    CLS_JSON:  str = "../Outputs/Gemini/gemini_doc_types.jsonl"
    CLS_CSV:   str = "../Outputs/Gemini/gemini_doc_types.csv"
    CLS_TABLE: str = "gemini_doc_types"            # ClickHouse + Spanner

    # ──────────────── DOCUMENT METADATA sinks (new) ────────────────
    META_JSON:  str = "../Outputs/Gemini/gemini_metadata.jsonl"
    META_CSV:   str = "../Outputs/Gemini/gemini_metadata.csv"
    META_TABLE: str = "document_metadata"           # ClickHouse + Spanner

    # ───────────────────────── Service account ──────────────────────────
    SA_KEY_PATH: str = (
        "/home/adrian/PycharmProjects/"
        "KYC-document-pipeline/moniepoint-document-verification-"
        "service-playground/ProcessorTraining/.gcp/adg-documentai-sa-key.json"
    )
    SCOPES: list[str] = field(
        default_factory=lambda: ["https://www.googleapis.com/auth/cloud-platform"]
    )

    # ─────────────────────────── ClickHouse ─────────────────────────────
    CH_HOST:  str = os.getenv("CH_HOST", "localhost")
    CH_PORT:  int = int(os.getenv("CH_PORT", "9000"))
    CH_USER:  str = os.getenv("CH_USER", "etl_writer")
    CH_PASS:  str = os.getenv("CH_PASS", "a?xBVq1!")
    CH_DB:    str = os.getenv("CH_DB", "utility_docs")

    # ──────────────────────────── Spanner ───────────────────────────────
    SPANNER_INSTANCE: str = "doc-instance"
    SPANNER_DATABASE: str = "utility_docs"
    # table names come from ENT_TABLE, CLS_TABLE, META_TABLE
