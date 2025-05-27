#!/usr/bin/env python3
"""
Compare entity-level confidence scores coming from
  • Gemini 2 Flash extraction  (gemini_entities.csv)
  • Custom rule-/OCR-based extractor (extracted_fields_with_labels.csv)

Outputs
-------
comparison_report.csv
confidence_scatter.png
boxplot_confidence_by_entity.png
mean_gap_by_entity.png
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.patches import Patch


# ─── 1) LOAD ──────────────────────────────────────────────────────────────────
gemini = pd.read_csv("../ProcessorTraining/gemini_entities.csv")
ex     = pd.read_csv("../ProcessorTraining/extracted_fields_with_labels.csv")

# ─── 2) UNPIVOT “ex” WIDE → LONG ─────────────────────────────────────────────
id_cols = ["gcs_uri"]
value_cols = {
    "Supply Address":        ("supply_address_value",    "supply_address_conf"),
    "Customer Name":         ("name_value",              "name_conf"),
    "Period":                ("period_value",            "period_conf"),
    "Meter Number":          ("meter_number_value",      "meter_number_conf"),
    "bill_month":            ("bill_month_value",        "bill_month_conf"),
    "customer_account":      ("customer_account_value",  "customer_account_conf"),
    "provider_acronym":      ("provider_acronym_value",  "provider_acronym_conf"),
    "service_address":       ("service_address_value",   "service_address_conf"),
    "meter_type":            ("meter_type_value",        "meter_type_conf"),
    "transaction_date":      ("transaction_date_value",  "transaction_date_conf"),
    "address":               ("address_value",           "address_conf"),
}

rows = []
for ent, (val_col, conf_col) in value_cols.items():
    tmp = ex[id_cols + [val_col, conf_col]].copy()
    tmp = tmp.rename(columns={val_col: "value_extracted",
                              conf_col: "confidence_extracted"})
    tmp["entity"] = ent
    rows.append(tmp)

ex_long = pd.concat(rows, ignore_index=True)

# ─── 3) MERGE GEMINI & EXTRACTOR RESULTS ─────────────────────────────────────
df = gemini.merge(
    ex_long,
    on=["gcs_uri", "entity"],
    how="outer",
    suffixes=("_gemini", "_extracted"),
)

# ─── 4) BASIC QUALITY CHECKS ─────────────────────────────────────────────────
df["value_match"] = df["value"] == df["value_extracted"]
df["conf_diff"]   = df["confidence"] - df["confidence_extracted"]

mismatches = df[~df["value_match"] | (df["conf_diff"].abs() > 0.10)]
print(f"Mismatches found: {len(mismatches)} rows")
df.to_csv("comparison_report.csv", index=False)

# ─── 5) POINT-BY-POINT SCATTER (OPTIONAL) ────────────────────────────────────
plt.figure(figsize=(8, 6))
for ent in df["entity"].unique():
    sub = df[df["entity"] == ent]
    plt.scatter(sub["confidence"],
                sub["confidence_extracted"],
                alpha=0.7,
                label=ent,
                s=30)

plt.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color="gray")
plt.xlabel("Gemini confidence")
plt.ylabel("Extractor confidence")
plt.title("Per-entity confidence comparison")
plt.legend(title="Entity", bbox_to_anchor=(1.05, 1), loc="upper left")
plt.grid(True, linestyle=":", alpha=0.5)
plt.tight_layout()
plt.savefig("confidence_scatter.png", dpi=300)
plt.close()

# ─── 6) SIDE-BY-SIDE BOX-PLOTS ───────────────────────────────────────────────
# Build a tidy “long” table with one score per row
long = pd.concat(
    [
        df[["entity", "confidence"]]
        .rename(columns={"confidence": "score"})
        .assign(source="Gemini"),
        df[["entity", "confidence_extracted"]]
        .rename(columns={"confidence_extracted": "score"})
        .assign(source="Extractor"),
    ],
    ignore_index=True,
        )

# Sort entities by Gemini median for nicer ordering
entity_order = (
    long.query("source == 'Gemini'")
    .groupby("entity")["score"]
    .median()
    .sort_values()
    .index
)
pos = np.arange(len(entity_order))
w   = 0.35   # box width

fig, ax = plt.subplots(figsize=(12, 6))

# plot two boxes per entity
for i, ent in enumerate(entity_order):
    g_data = long.query("entity == @ent and source == 'Gemini'")["score"].dropna()
    e_data = long.query("entity == @ent and source == 'Extractor'")["score"].dropna()

    ax.boxplot(g_data,
               positions=[i - w/2],
               widths=w,
               patch_artist=True,
               boxprops=dict(facecolor="tab:blue", alpha=0.6))
    ax.boxplot(e_data,
               positions=[i + w/2],
               widths=w,
               patch_artist=True,
               boxprops=dict(facecolor="tab:orange", alpha=0.6))

ax.set_xticks(pos, entity_order, rotation=90)
ax.set_ylabel("Confidence score")
ax.set_title("Gemini vs Extractor — distribution of scores by entity")
ax.yaxis.set_major_locator(MaxNLocator(10))
legend_handles = [Patch(facecolor="tab:blue",   label="Gemini"),
                  Patch(facecolor="tab:orange", label="Extractor")]
ax.legend(handles=legend_handles, loc="upper left")
ax.grid(axis="y", linestyle=":", alpha=0.4)
plt.tight_layout()
plt.savefig("boxplot_confidence_by_entity.png", dpi=300)
plt.close()

# ─── 7) DIVERGING BAR: MEAN SCORE GAP ────────────────────────────────────────
agg = (
    df.groupby("entity")
    .agg(gemini_mean=("confidence", "mean"),
         extractor_mean=("confidence_extracted", "mean"))
)
agg["delta"] = agg["gemini_mean"] - agg["extractor_mean"]
agg = agg.sort_values("delta")

fig, ax = plt.subplots(figsize=(9, max(4, len(agg) * 0.35)))
colors = ["tab:blue" if d > 0 else "tab:orange" for d in agg["delta"]]
ax.barh(agg.index, agg["delta"], color=colors)
ax.axvline(0, color="k", linewidth=0.8)
ax.set_xlabel("Gemini – Extractor mean confidence")
ax.set_title("Average confidence gap by entity\n(positive ⇒ Gemini higher)")
plt.tight_layout()
plt.savefig("mean_gap_by_entity.png", dpi=300)
plt.close()

print("Plots saved:\n"
      "  • confidence_scatter.png\n"
      "  • boxplot_confidence_by_entity.png\n"
      "  • mean_gap_by_entity.png")
