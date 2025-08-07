#!/usr/bin/env python3
"""
Per-document entity counts for Gemini vs Extractor
=================================================

INPUT
    ../ProcessorTraining/gemini_entities.csv
    ../ProcessorTraining/extracted_fields_with_labels.csv

OUTPUT
    doc_entity_counts.csv      # count table
    doc_entity_counts.png      # bar-chart visual
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ─── CONFIG ────────────────────────────────────────────────────────────────────
DATA_DIR      = Path("../ProcessorTraining")
GEMINI_CSV    = DATA_DIR / "gemini_entities.csv"
EXTRACTOR_CSV = DATA_DIR / "extracted_fields_with_labels.csv"

# ─── 1) LOAD ───────────────────────────────────────────────────────────────────
gemini = pd.read_csv(GEMINI_CSV)
ex_raw = pd.read_csv(EXTRACTOR_CSV)

# ─── 2) WIDE → LONG CONVERSION FOR EXTRACTOR ──────────────────────────────────
value_cols = {
    "Supply Address":        "supply_address_value",
    "Customer Name":         "name_value",
    "Period":                "period_value",
    "Meter Number":          "meter_number_value",
    "bill_month":            "bill_month_value",
    "customer_account":      "customer_account_value",
    "provider_acronym":      "provider_acronym_value",
    "service_address":       "service_address_value",
    "meter_type":            "meter_type_value",
    "transaction_date":      "transaction_date_value",
    "address":               "address_value",
}

rows = []
for ent, col in value_cols.items():
    tmp = ex_raw[["gcs_uri", col]].rename(columns={col: "value"})
    tmp = tmp.dropna(subset=["value"])
    tmp["entity"] = ent
    rows.append(tmp[["gcs_uri", "entity"]])

ex_long = pd.concat(rows, ignore_index=True)

# ─── 3) PER-DOCUMENT COUNTS ───────────────────────────────────────────────────
gemini_doc_counts = (
    gemini.groupby("gcs_uri")
    .size()
    .rename("gemini_entity_count")
)

extractor_doc_counts = (
    ex_long.groupby("gcs_uri")
    .size()
    .rename("extractor_entity_count")
)

doc_counts = (
    pd.concat([gemini_doc_counts, extractor_doc_counts], axis=1)
    .fillna(0)
    .astype(int)
    .sort_index()
)

doc_counts.to_csv("doc_entity_counts.csv")
print("✓ Saved per-document counts ➜ doc_entity_counts.csv")

# ─── 4) PLOT ──────────────────────────────────────────────────────────────────
# If you have many documents, consider sub-setting first:
# doc_counts = doc_counts.head(25)   # keep first 25 for readability

x = np.arange(len(doc_counts))
width = 0.40

fig, ax = plt.subplots(figsize=(max(6, len(doc_counts) * 0.35), 5))

ax.bar(x - width/2, doc_counts["gemini_entity_count"],  width,
       label="Gemini", color="tab:blue")
ax.bar(x + width/2, doc_counts["extractor_entity_count"], width,
       label="Extractor", color="tab:orange")

# Shorten very long gcs_uri strings for the x-axis
short_labels = (
        doc_counts.index
        .str.replace(r"^.*/", "", regex=True)   # keep only last path component
        .str.slice(0, 25) + "…"                 # truncate nicely
)

ax.set_xticks(x, short_labels, rotation=90)
ax.set_ylabel("Entities extracted")
ax.set_title("Entities per document (Gemini vs Extractor)")
ax.legend()
ax.yaxis.set_major_locator(MaxNLocator(integer=True))
ax.grid(axis="y", linestyle=":", alpha=0.4)

plt.tight_layout()
plt.savefig("doc_entity_counts.png", dpi=300)
plt.close()

print("✓ Plot saved ➜ doc_entity_counts.png")
