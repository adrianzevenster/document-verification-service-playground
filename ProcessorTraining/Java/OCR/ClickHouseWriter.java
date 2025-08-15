package com.moniepoint.dvs.processor.db;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import java.util.Properties;

import com.moniepoint.dvs.component.ConfigurationManager;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Minimal helper that:
 *   ① opens a JDBC connection to ClickHouse
 *   ② ensures {database, table} exist (similar DDL to the Python version)
 *   ③ lets callers insert one row (gcs_uri + 33 columns) in the order supplied
 *
 * *It is intentionally lightweight – keep connection pooling, batching, etc.
 *  in a higher-level service if you need it.*
 */
public final class ClickHouseWriter implements AutoCloseable {
    private static final Logger log = LogManager.getLogger(ClickHouseWriter.class);

    /* ─── configuration keys ─────────────────────────────────────────── */
    private static final String CFG_HOST   = "clickhouse.host";   // localhost
    private static final String CFG_PORT   = "clickhouse.port";   // 9000
    private static final String CFG_DB     = "clickhouse.db";     // utility_docs
    private static final String CFG_USER   = "clickhouse.user";   // etl_writer
    private static final String CFG_PASS   = "clickhouse.pass";   // a?xBVq1!
    private static final String CFG_TABLE  = "clickhouse.table";  // extracted_fields

    /* ─── column order must exactly match the Python CSV header ───────── */
    public static final List<String> COL_ORDER = List.of(
            "gcs_uri",
            /* supply_address  */ "supply_address_label","supply_address_value","supply_address_conf",
            "name_label","name_value","name_conf",
            "period_label","period_value","period_conf",
            "meter_number_label","meter_number_value","meter_number_conf",
            "bill_month_label","bill_month_value","bill_month_conf",
            "customer_account_label","customer_account_value","customer_account_conf",
            "provider_acronym_label","provider_acronym_value","provider_acronym_conf",
            "service_address_label","service_address_value","service_address_conf",
            "meter_type_label","meter_type_value","meter_type_conf",
            "transaction_date_label","transaction_date_value","transaction_date_conf",
            "address_label","address_value","address_conf"
    );

    /* ─── members ─────────────────────────────────────────────────────── */
    private final ConfigurationManager cfg;
    private final Connection conn;
    private final String     tableFqn;            // db.table
    private final PreparedStatement insertStmt;   // prepared once, reused

    public ClickHouseWriter(ConfigurationManager cfg) throws Exception {
        this.cfg = cfg;

        // Build JDBC URL
        String host = cfg.getConfiguration(CFG_HOST, "localhost");
        String port = cfg.getConfiguration(CFG_PORT, "9000");
        String db   = cfg.getConfiguration(CFG_DB,   "utility_docs");
        String user = cfg.getConfiguration(CFG_USER, "etl_writer");
        String pass = cfg.getConfiguration(CFG_PASS, "password");

        this.tableFqn = db + "." + cfg.getConfiguration(CFG_TABLE, "extracted_fields");

        String url = String.format("jdbc:clickhouse://%s:%s/%s", host, port, db);
        Properties props = new Properties();
        props.setProperty("user",     user);
        props.setProperty("password", pass);
        props.setProperty("send_receive_timeout", "30");   // parity with Python

        // driver class is auto-loaded via SPI (artifact: com.clickhouse:clickhouse-jdbc)
        this.conn = new com.clickhouse.jdbc.ClickHouseDataSource(url, props).getConnection();

        ensureSchemaExists(db);
        this.insertStmt = buildInsert();
        log.info("✅ ClickHouse ready at {}", url);
    }

    /* CREATE DATABASE / TABLE if needed – mirrors the Python DDL  */
    private void ensureSchemaExists(String db) throws SQLException {
        try (var st = conn.createStatement()) {
            st.execute("CREATE DATABASE IF NOT EXISTS " + db);
            StringBuilder body = new StringBuilder();
            for (String c : COL_ORDER) {
                if (body.length() > 0) body.append(", ");
                body.append(c).append(c.endsWith("_conf") ? " Float32" : " String");
            }
            st.execute(
                "CREATE TABLE IF NOT EXISTS " + tableFqn + " ( " + body +
                " ) ENGINE = MergeTree() ORDER BY gcs_uri"
            );
        }
    }

    /* Build INSERT … VALUES (?, ?, …) prepared statement  */
    private PreparedStatement buildInsert() throws SQLException {
        StringBuilder q = new StringBuilder("INSERT INTO ").append(tableFqn).append(" VALUES (");
        for (int i = 0; i < COL_ORDER.size(); i++) {
            if (i > 0) q.append(',');
            q.append('?');
        }
        q.append(')');
        return conn.prepareStatement(q.toString());
    }

    /** Insert one row (values list length **must equal** {@link #COL_ORDER}. */
    public void writeRow(List<Object> values) {
        if (values.size() != COL_ORDER.size()) {
            log.error("Expected {} columns, got {}", COL_ORDER.size(), values.size());
            return;
        }
        try {
            for (int i = 0; i < values.size(); i++) {
                insertStmt.setObject(i + 1, values.get(i));
            }
            insertStmt.executeUpdate();
        } catch (SQLException e) {
            log.warn("⚠️ ClickHouse insert failed", e);
        }
    }

    @Override public void close() throws Exception { conn.close(); }
}
