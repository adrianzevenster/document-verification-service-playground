import pandas as pd
import matplotlib.pyplot as plt

# 1) load
gemini = pd.read_csv("../ProcessorTraining/gemini_entities.csv")
ex     = pd.read_csv("../ProcessorTraining/extracted_fields_with_labels.csv")

# 2) unpivot the wide file
id_cols = ["gcs_uri"]
value_cols = {
    "Supply Address": ("supply_address_value", "supply_address_conf"),
    "Customer Name":  ("name_value",            "name_conf"),
    "Period":         ("period_value",         "period_conf"),
    "Meter Number":   ("meter_number_value",   "meter_number_conf"),
    "bill_month":     ("bill_month_value",     "bill_month_conf"),
    "customer_account": ("customer_account_value", "customer_account_conf"),
    "provider_acronym": ("provider_acronym_value", "provider_acronym_conf"),
    "service_address": ("service_address_value", "service_address_conf"),
    "meter_type":     ("meter_type_value",     "meter_type_conf"),
    "transaction_date": ("transaction_date_value", "transaction_date_conf"),
    "address":         ("address_value",         "address_conf")


}


rows = []
for ent, (val_col, conf_col) in value_cols.items():
    tmp = ex[id_cols + [val_col, conf_col]].copy()
    tmp = tmp.rename(columns={
        val_col: "value_extracted",
        conf_col: "confidence_extracted"
    })
    tmp["entity"] = ent
    rows.append(tmp)
ex_long = pd.concat(rows, ignore_index=True)

# 3) (optional) normalize entity names
# mapping = {"Name": "Customer Name", ...}
# ex_long["entity"] = ex_long["entity"].replace(mapping)

# 4) merge
df = gemini.merge(
    ex_long,
    on=["gcs_uri", "entity"],
    how="outer",
    suffixes=("_gemini", "_extracted")
)

# 5) compare
df["value_match"] = df["value"] == df["value_extracted"]
df["conf_diff"]  = df["confidence"] - df["confidence_extracted"]

# 6) inspect mismatches
mismatches = df[~df["value_match"] | (df["conf_diff"].abs() > 0.1)]
print("Mismatches:\n", mismatches)

# 7) save merged results
df.to_csv("comparison_report.csv", index=False)


# ── 8) grouped scatter-plot per entity ────────────────────────────────────────────

plt.figure(figsize=(8, 6))

for ent in df["entity"].unique():
    sub = df[df["entity"] == ent]
    plt.scatter(
        sub["confidence"],
        sub["confidence_extracted"],
        alpha=0.7,
        label=ent
    )

# diagonal y=x reference
plt.plot([0, 1], [0, 1], linestyle="--")

plt.xlabel("Gemini Confidence")
plt.ylabel("Extracted Confidence")
plt.title("Per-Entity Confidence Comparison")
plt.legend(title="Entity Type")
plt.grid(True)

# save &/or show
plt.savefig("confidence_comparison_by_entity.png", dpi=300)
plt.show()

plt.figure(figsize=(9, 6))
for ent in df["entity"].unique():
    sub = df[df["entity"] == ent]["confidence"].dropna()
    plt.hist(
        sub,
        bins=20,
        alpha=0.6,
        label=ent,
        edgecolor="black",
        linewidth=0.5,
    )

plt.title("Gemini confidence distributions by entity")
plt.xlabel("Gemini confidence score")
plt.ylabel("Frequency")
plt.legend(title="Entity", fontsize="small")
plt.grid(axis="y", linestyle=":", alpha=0.4)
plt.tight_layout()
plt.savefig("gemini_confidence_by_entity.png", dpi=300)
plt.show()   # uncomment if you still want an interactive window

# --- 9) EXTRACTED-ONLY (‘ex’) confidence per entity --------------------------
plt.figure(figsize=(9, 6))
for ent in df["entity"].unique():
    sub = df[df["entity"] == ent]["confidence_extracted"].dropna()
    plt.hist(
        sub,
        bins=20,
        alpha=0.6,
        label=ent,
        edgecolor="black",
        linewidth=0.5,
    )

plt.title("Extractor confidence distributions by entity")
plt.xlabel("Extractor confidence score")
plt.ylabel("Frequency")
plt.legend(title="Entity", fontsize="small")
plt.grid(axis="y", linestyle=":", alpha=0.4)
plt.tight_layout()
plt.savefig("extracted_confidence_by_entity.png", dpi=300)
plt.show()