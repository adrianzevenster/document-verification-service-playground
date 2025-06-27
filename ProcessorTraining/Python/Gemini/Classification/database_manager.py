from clickhouse_driver import Client as CHClient
from google.cloud import spanner
from .config import Config


class DatabaseManager:
    """Creates / holds ClickHouse + Spanner handles (if reachable)."""

    def __init__(self, creds):
        self.creds       = creds
        self.ch          = None
        self.spanner_db  = None
        self.ch_ok       = False
        self.sp_ok       = False
        self._init_clickhouse()
        self._init_spanner()

    # ──────────────────────── ClickHouse ────────────────────────────── #
    def _init_clickhouse(self):
        try:
            ctl = CHClient(
                host=Config.CH_HOST,
                port=Config.CH_PORT,
                user=Config.CH_USER,
                password=Config.CH_PASS,
                send_receive_timeout=30,
            )

            # ① ensure database
            ctl.execute(f"CREATE DATABASE IF NOT EXISTS {Config.CH_DB}")

            # ② entity-extraction table
            ctl.execute(f"""
                CREATE TABLE IF NOT EXISTS {Config.CH_DB}.{Config.ENT_TABLE} (
                  gcs_uri       String,
                  page          UInt64,
                  document_type String,
                  entity        String,
                  value         String,
                  confidence    Float32
                )
                ENGINE = MergeTree()
                ORDER BY (gcs_uri, page, document_type, entity)
            """)

            # ③ classifier table
            ctl.execute(f"""
                CREATE TABLE IF NOT EXISTS {Config.CH_DB}.{Config.CLS_TABLE} (
                  gcs_uri       String,
                  document_type String
                )
                ENGINE = MergeTree()
                ORDER BY (gcs_uri)
            """)

            # ④ open final connection scoped to the DB
            self.ch = CHClient(
                host=Config.CH_HOST,
                port=Config.CH_PORT,
                user=Config.CH_USER,
                password=Config.CH_PASS,
                database=Config.CH_DB,
                send_receive_timeout=30,
            )
            self.ch.execute("SELECT 1")
            self.ch_ok = True
            print(f"✅ ClickHouse TCP OK @{Config.CH_HOST}:{Config.CH_PORT}")

        except Exception as e:
            print("⚠️ ClickHouse unavailable – skipping:", e)

    # ───────────────────────── Spanner ──────────────────────────────── #
    def _init_spanner(self):
        try:
            sp_client = spanner.Client(
                project=Config.PROJECT_ID, credentials=self.creds
            )
            instance = sp_client.instance(Config.SPANNER_INSTANCE)
            db       = instance.database(Config.SPANNER_DATABASE)

            ddl_entities = f"""
              CREATE TABLE {Config.ENT_TABLE} (
                gcs_uri       STRING(MAX) NOT NULL,
                page          INT64,
                document_type STRING(MAX),
                entity        STRING(MAX),
                value         STRING(MAX),
                confidence    FLOAT64
              ) PRIMARY KEY (gcs_uri, page, document_type, entity)
            """

            ddl_classes = f"""
              CREATE TABLE {Config.CLS_TABLE} (
                gcs_uri       STRING(MAX) NOT NULL,
                document_type STRING(MAX)
              ) PRIMARY KEY (gcs_uri)
            """

            # run both statements in one DDL update; Spanner skips if exists
            db.update_ddl([ddl_entities, ddl_classes]).result()

            self.spanner_db = db
            self.sp_ok      = True
            print(f"✅ Spanner tables ensured @ {Config.SPANNER_DATABASE}/"
                  f"({Config.ENT_TABLE}, {Config.CLS_TABLE})")

        except Exception as e:
            print("⚠️ Spanner unavailable or no permission – skipping:", e)
