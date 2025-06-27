import os, csv, json
from .config           import Config
from .database_manager import DatabaseManager

class ClassificationWriter:
    """Writes one row per DOCUMENT (not per page) to CSV/JSON/DB."""

    def __init__(self, csv_path: str, json_path: str, db: DatabaseManager):
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self.csv_fh  = open(csv_path,  "w", newline="", encoding="utf-8")
        self.json_fh = open(json_path, "w",           encoding="utf-8")
        self.writer  = csv.DictWriter(
            self.csv_fh,
            fieldnames=["gcs_uri", "document_type"],
        )
        self.writer.writeheader()
        self.db = db

    def write(self, gcs_uri: str, doc_type: str):
        row = {"gcs_uri": gcs_uri, "document_type": doc_type}

        # --- CSV / JSONL
        self.writer.writerow(row)
        self.json_fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        # --- ClickHouse
        if self.db.ch_ok:
            try:
                self.db.ch.execute(
                    f"INSERT INTO {Config.CLS_TABLE} (gcs_uri, document_type) VALUES",
                    [(gcs_uri, doc_type)],
                )
            except Exception as e:
                print("  ⚠️ CH write failed (CLS):", e)

        # --- Spanner
        if self.db.sp_ok:
            def _txn(txn):
                txn.insert(
                    table   = Config.CLS_TABLE,
                    columns = ["gcs_uri", "document_type"],
                    values  = [(gcs_uri, doc_type)],
                )
            try:
                self.db.spanner_db.run_in_transaction(_txn)
            except Exception as e:
                print("  ⚠️ Spanner write failed (CLS):", e)

    def close(self):
        self.csv_fh.close()
        self.json_fh.close()
