package com.moniepoint.dvs.processor.db;

import java.util.Arrays;
import java.util.List;

import com.google.api.gax.core.FixedCredentialsProvider;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.moniepoint.dvs.component.ConfigurationManager;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Very small helper that:
 *   ① opens a Cloud Spanner {@link DatabaseClient}
 *   ② lets callers insert one row (same order as ClickHouseWriter)
 *
 * Schema creation is *not* included – manage DDL externally, exactly like the
 * original Python script (`_ensure_spanner_db_and_table` was a no-op).
 */
public final class SpannerWriter implements AutoCloseable {
    private static final Logger log = LogManager.getLogger(SpannerWriter.class);

    /* ─── configuration keys ─────────────────────────────────────────── */
    private static final String CFG_PROJECT   = "spanner.project";   // adg-delivery-moniepoint
    private static final String CFG_INSTANCE  = "spanner.instance";  // doc-instance
    private static final String CFG_DATABASE  = "spanner.database";  // utility_docs
    private static final String CFG_TABLE     = "spanner.table";     // extracted_fields
    private static final String CFG_SA_JSON   = "spanner.serviceaccount.key";

    private final DatabaseClient dbClient;
    private final String         table;
    public  static final List<String> COL_ORDER = ClickHouseWriter.COL_ORDER; // identical order

    public SpannerWriter(ConfigurationManager cfg) throws Exception {
        this.table = cfg.getConfiguration(CFG_TABLE, "extracted_fields");

        // credentials (service-account JSON string comes from ConfigurationManager)
        String saJson = cfg.getConfiguration(CFG_SA_JSON, "");
        GoogleCredentials creds = GoogleCredentials
                .fromStream(new java.io.ByteArrayInputStream(saJson.getBytes()))
                .createScoped(Arrays.asList("https://www.googleapis.com/auth/cloud-platform"));

        SpannerOptions opts = SpannerOptions.newBuilder()
                .setProjectId(cfg.getConfiguration(CFG_PROJECT, "my-gcp-project"))
                .setCredentials(creds)
                .build();
        Spanner spanner = opts.getService();
        this.dbClient   = spanner.getDatabaseClient(
                opts.getInstanceAdminClient()
                    .newInstanceId(cfg.getConfiguration(CFG_INSTANCE, "doc-instance"))
                    .database(cfg.getConfiguration(CFG_DATABASE, "utility_docs"))
        );
        log.info("✅ Spanner ready (instance {}, db {})",
                 cfg.getConfiguration(CFG_INSTANCE, ""), cfg.getConfiguration(CFG_DATABASE, ""));
    }

    /** Insert one row (values list length **must equal** {@link #COL_ORDER}). */
    public void writeRow(List<Object> values) {
        if (values.size() != COL_ORDER.size()) {
            log.error("Expected {} columns, got {}", COL_ORDER.size(), values.size());
            return;
        }
        try {
            Mutation.WriteBuilder wr = Mutation.newInsertBuilder(table);
            for (int i = 0; i < COL_ORDER.size(); i++) {
                Object v = values.get(i);
                if (i == 0 || (i - 1) % 3 != 2) { // gcs_uri or label/value → STRING
                    wr.set(COL_ORDER.get(i)).to(v == null ? "" : v.toString());
                } else {                           // *_conf column → FLOAT64
                    wr.set(COL_ORDER.get(i)).to(v == null ? null : Double.valueOf(v.toString()));
                }
            }
            dbClient.write(java.util.Collections.singletonList(wr.build()));
        } catch (Exception e) {
            log.warn("⚠️ Spanner insert failed", e);
        }
    }
    @Override public void close() { /* Spanner is a shared singleton; nothing to close */ }
}
