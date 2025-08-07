import csv, json, os
from pathlib import Path
from typing import Dict

class MetaWriter:
    """Write one <gcs_uri, key, value> row per metadata field."""
    COLS = ["gcs_uri", "meta_key", "meta_value"]

    def __init__(self, csv_path: str, jsonl_path: str):
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)

        self._csv = open(csv_path, "w", newline="", encoding="utf-8")
        self._jsonl = open(jsonl_path, "w", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv, fieldnames=self.COLS)
        self._csv_writer.writeheader()

    def write(self, gcs_uri: str, meta: Dict[str, str]):
        for k, v in meta.items():
            row = {"gcs_uri": gcs_uri, "meta_key": k, "meta_value": v}
            self._csv_writer.writerow(row)
            self._jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")

    def close(self):
        self._csv.close()
        self._jsonl.close()
