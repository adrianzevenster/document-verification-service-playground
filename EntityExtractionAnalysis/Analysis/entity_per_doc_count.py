#!/usr/bin/env python3
"""
Count documents + entity occurrences and plot the results
---------------------------------------------------------
INPUT
    ../ProcessorTraining/gemini_entities.csv
    ../ProcessorTraining/extracted_fields_with_labels.csv

OUTPUT
    entity_counts.csv
    doc_count.png
    entity_counts_bar.png
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

# ─── 1) LOAD FILES ─────────────────────────────────────────────────────────────
gemini = pd.read_csv(GEMINI_CSV)
ex_raw = pd.read_csv(EXTRACTOR_CSV)

# ─── 2) DOCUMENT COUNTS ───────────────────────────────────────────────────────
docs_gemini = gemini["gcs_uri"].nunique()
docs_ex     = ex_raw["gcs_uri"].nunique()

# ─── 3) ENTITY COUNTS ─────────────────────────────────────────────────────────
# 3-a  Gemini (already long)
gemini_counts = (
    gemini["entity"]
    .value_counts()
    .rename_axis("entity")
    .rename("gemini_count")
)

# 3-b  Extractor (wide → long for counting)
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

ex_counts = (
    ex_long["entity"]
    .value_counts()
    .rename_axis("entity")
    .rename("extractor_count")
)

# ─── 4) MERGE FOR COMPARISON & SAVE CSV ───────────────────────────────────────
entity_counts = (
    pd.concat([gemini_counts, ex_counts], axis=1)
    .fillna(0, downcast="infer")
    .astype(int)
    .sort_index()
)
entity_counts.to_csv("entity_counts.csv")

# ─── 5) PLOT A – DOCUMENT COUNTS ──────────────────────────────────────────────
plt.figure(figsize=(5, 4))
plt.bar(["Gemini", "Extractor"], [docs_gemini, docs_ex])
plt.ylabel("Documents processed")
plt.title("Document count per pipeline")
plt.grid(axis="y", linestyle=":", alpha=0.4)
plt.tight_layout()
plt.savefig("doc_count.png", dpi=300)
plt.close()

# ─── 6) PLOT B – ENTITY COUNTS BAR CHART ──────────────────────────────────────
x = np.arange(len(entity_counts))
width = 0.35

fig, ax = plt.subplots(figsize=(14, 6))
ax.bar(x - width/2, entity_counts["gemini_count"],  width, label="Gemini")
ax.bar(x + width/2, entity_counts["extractor_count"], width, label="Extractor")

ax.set_xticks(x, entity_counts.index, rotation=90)
ax.set_ylabel("Occurrences")
ax.set_title("Entity occurrences by pipeline")
ax.legend()
ax.yaxis.set_major_locator(MaxNLocator(integer=True))
ax.grid(axis="y", linestyle=":", alpha=0.4)
plt.tight_layout()
plt.savefig("entity_counts_bar.png", dpi=300)
plt.close()

print("✓ Counts written to entity_counts.csv")
print("✓ Plots saved: doc_count.png, entity_counts_bar.png")
