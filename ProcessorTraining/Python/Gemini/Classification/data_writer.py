import os, csv, json
from .config            import Config
from .database_manager  import DatabaseManager

class DataWriter:
    """Streams rows → CSV, JSONL, ClickHouse and Spanner (if available)."""

    def __init__(self, csv_path: str, json_path: str, db: DatabaseManager):
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self.csv_fh  = open(csv_path,  "w", newline="", encoding="utf-8")
        self.json_fh = open(json_path, "w",           encoding="utf-8")
        self.writer  = csv.DictWriter(
            self.csv_fh,
            fieldnames=[
                "gcs_uri", "page", "document_type",
                "entity",  "value", "confidence",
            ],
        )
        self.writer.writeheader()
        self.db = db

    def write(self, row: dict):
        print("[DataWriter] row:", row)
        # CSV / JSONL
        self.writer.writerow(row)
        self.json_fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        # ClickHouse
        if self.db.ch_ok:
            try:
                self.db.ch.execute(
                    f"INSERT INTO {Config.CH_TABLE} "
                    "(gcs_uri, page, document_type, entity, value, confidence) VALUES",
                    [(row["gcs_uri"], row["page"], row["document_type"],
                      row["entity"], row["value"], row["confidence"])],
                )
            except Exception as e:
                print("  ⚠️ CH write failed:", e)

        # Spanner
        if self.db.sp_ok:
            def _txn(txn):
                txn.insert(
                    table   = Config.SPANNER_TABLE,
                    columns = [
                        "gcs_uri", "page", "document_type",
                        "entity",  "value", "confidence",
                    ],
                    values=[(
                        row["gcs_uri"], row["page"], row["document_type"],
                        row["entity"],  row["value"], row["confidence"],
                    )],
                )
            try:
                self.db.spanner_db.run_in_transaction(_txn)
            except Exception as e:
                print("  ⚠️ Spanner write failed:", e)

    def close(self):
        self.csv_fh.close()
        self.json_fh.close()
