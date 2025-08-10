from clickhouse_driver import Client as CHClient
from google.cloud import spanner
from google.api_core.exceptions import FailedPrecondition
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

            # Helper: check if a table exists
            def _table_exists(table_name: str) -> bool:
                with db.snapshot() as snap:
                    it = snap.execute_sql(
                        """
                        SELECT 1
                        FROM INFORMATION_SCHEMA.TABLES
                        WHERE TABLE_SCHEMA = '' AND TABLE_NAME = @t
                            LIMIT 1
                        """,
                        params={"t": table_name},
                        param_types={"t": spanner.param_types.STRING},
                    )
                    return any(it)

            # Build DDL list only for missing tables
            ddls = []
            if not _table_exists(Config.ENT_TABLE):
                ddls.append(ddl_entities)
            if not _table_exists(Config.CLS_TABLE):
                ddls.append(ddl_classes)

            # Make the handle available regardless of whether DDL runs
            self.spanner_db = db
            self.sp_ok      = True

            if ddls:
                try:
                    db.update_ddl(ddls).result()
                    print(f"✅ Spanner tables created: {', '.join( n for n,_ in [(Config.ENT_TABLE, ddl_entities), (Config.CLS_TABLE, ddl_classes)] if n in ''.join(ddls))}")
                except FailedPrecondition as e:
                    # If a race created the table(s) meanwhile, ignore the duplicate error
                    if "Duplicate name in schema" in str(e):
                        print("ℹ️ Spanner tables already exist (race), continuing.")
                    else:
                        raise

            print(f"✅ Spanner ready @ {Config.SPANNER_DATABASE} "
                  f"({Config.ENT_TABLE}, {Config.CLS_TABLE})")

        except Exception as e:
            # Leave sp_ok=False so writers skip Spanner cleanly
            self.sp_ok = False
            print("⚠️ Spanner unavailable or no permission – skipping:", e)