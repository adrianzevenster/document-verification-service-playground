package com.moniepoint.dvs.processor.entities;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.Locale;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import com.google.api.gax.core.FixedCredentialsProvider;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.documentai.v1.Document;
import com.google.cloud.documentai.v1.DocumentProcessorServiceClient;
import com.google.cloud.documentai.v1.DocumentProcessorServiceSettings;
import com.google.cloud.documentai.v1.ProcessRequest;
import com.google.cloud.documentai.v1.RawDocument;
import com.google.cloud.documentai.v1.ProcessResponse;
import com.google.cloud.documentai.v1.ProcessorName;
import com.google.protobuf.ByteString;
import com.moniepoint.dvs.component.ConfigurationManager;
import com.moniepoint.dvs.processor.Entity;

/**
 * <p>
 * This class is used to extract entities from an image using Google
 * Cloud's DocumentAI OCR API.
 * </p>
 *
 * TODO: wire into wider workflow
 * JIRA:
 * https://teamapt.atlassian.net/jira/software/projects/DVSS/boards/1744/timeline?selectedIssue=DVSS-92
 */
@Component
public class DocumentAiImageOcrEntityExtractor {
    private final ConfigurationManager configurationManager;
    private String PROJECT_ID;
    private String GOOGLE_CLOUD_REGION;
    private String PROCESSOR_ID;
    private String INPUT_FILES_BUCKET_NAME;
    private String INPUT_FILES_DIRECTORY;
    private String GCP_SERVICE_ACCOUNT_KEY;

    private static final String CREDENTIALS_SCOPE = "https://www.googleapis.com/auth/cloud-platform";
    private static final String DOCUMENTAI_ENDPOINT_TEMPLATE = "%s-documentai.googleapis.com:443";

    private static final Map<String, String> KNOWN_LABELS = createKeyPatterns();

    // TODO: think of a better way of definign these patterns for entities
    private static Map<String, String> createKeyPatterns() {
        Map<String, String> patterns = new HashMap<>();
        patterns.put("supply_address", "(supply|bill delivery)\\s*address");
        patterns.put("name", "(customer|account)?\\s*name");
        patterns.put("period", "period");
        patterns.put("meter_number", "meter\\s*(number|no\\.?|num|#)?");
        patterns.put("bill_month", "bill\\s*month");
        patterns.put("customer_account",
                "(customer|old)?\\s*account(\\s*no\\.?| number| #)?");
        patterns.put("provider_acronym", "provider acronym");
        patterns.put("service_address", "service address");
        patterns.put("meter_type", "meter\\s*type");
        patterns.put("transaction_date", "(transaction|purchase)\\s*date");
        patterns.put("address", "\\baddress\\b");
        return patterns;
    }

    private static final List<String> HEADER_ORDER = List.of(
            "supply_address", "name", "period", "meter_number",
            "bill_month", "customer_account", "provider_acronym",
            "service_address", "meter_type", "transaction_date", "address");

    private static final Set<String> VALUES_LIKE_NONE = Set.of("n/a", "na", "-", "=", "null", "none");
    private static final Set<String> TEXT_FIELDS = Set.of("supply_address", "service_address", "address", "name");
    private static final Pattern PURE_DIGITS = Pattern.compile("^\\d+$");
    private static final Set<String> METER_SKIP_WORDS = Set.of("old", "previous", "multiplier", "account", "address",
            "adc");

    private static final Logger logger = LogManager.getLogger(DocumentAiImageOcrEntityExtractor.class);

    /**
     * Constructor with a configuration manager, which is used to retrieve
     * configuration items.
     *
     * @param configurationManager The ConfigurationManager instance to use
     */
    @Autowired
    public DocumentAiImageOcrEntityExtractor(ConfigurationManager configurationManager) {
        this.configurationManager = configurationManager;
        this.PROJECT_ID = configurationManager.getConfiguration("ocr.project.id");
        this.GOOGLE_CLOUD_REGION = configurationManager.getConfiguration("ocr.cloud.region");
        this.PROCESSOR_ID = configurationManager.getConfiguration("ocr.processor.id");
        this.INPUT_FILES_BUCKET_NAME = configurationManager.getConfiguration("ocr.input.documents.bucket");
        this.INPUT_FILES_DIRECTORY = configurationManager.getConfiguration("ocr.input.documents.directory");
        this.GCP_SERVICE_ACCOUNT_KEY = configurationManager.getConfiguration("ocr.serviceaccount.key");
    }

    /**
     * Get the configuration manager.
     *
     * @return The ConfigurationManager used for this instance.
     */
    public ConfigurationManager getConfigurationManager() {
        return this.configurationManager;
    }

    /**
     * Authenticates, initialises clients, walks every object in the configured
     * GCS folder and appends one row per file to the CSV output.
     *
     * @throws IOException if credentials cannot be read or output file can't
     *                     be written
     */
    public void runAgainstAllDocumentsInBucket() throws IOException {
        GoogleCredentials creds = loadCredentials();
        Storage storage = initStorageClient(creds);
        DocumentProcessorServiceSettings docAiSettings = initDocumentAiSettings(creds);

        try (DocumentProcessorServiceClient docAiClient = DocumentProcessorServiceClient.create(docAiSettings)) {

            String processorName = buildProcessorName();
            processAllDocuments(storage, docAiClient, processorName);
            logger.info("Done");
        }
    }

    /**
     * Loads service-account credentials from the JSON key.
     *
     * @return authenticated GoogleCredentials
     * @throws IOException if key file can't be read
     */
    private GoogleCredentials loadCredentials() throws IOException {
        if (GCP_SERVICE_ACCOUNT_KEY == null || GCP_SERVICE_ACCOUNT_KEY.isEmpty()) {
            throw new IllegalStateException(
                    "GCP_SERVICE_ACCOUNT_KEY configuration item is not set - please put it into the environment.");
        }

        try (ByteArrayInputStream bais = new ByteArrayInputStream(GCP_SERVICE_ACCOUNT_KEY.getBytes())) {
            return GoogleCredentials.fromStream(bais)
                    .createScoped(List.of(CREDENTIALS_SCOPE));
        }
    }

    /**
     * Initializes the Google Cloud Storage client.
     *
     * @param creds Credentials for authorization on Google Cloud.
     * @return The client to use to access Google Cloud Storage.
     */
    private Storage initStorageClient(GoogleCredentials creds) {
        return StorageOptions.newBuilder()
                .setProjectId(PROJECT_ID)
                .setCredentials(creds)
                .build()
                .getService();
    }

    /**
     * Initializes Document AI client settings.
     *
     * @param creds Credentials for authorization on Google Cloud.
     * @return Settings for the Document AI client.
     * @throws IOException If creating the settings fails.
     */
    private DocumentProcessorServiceSettings initDocumentAiSettings(GoogleCredentials creds)
            throws IOException {
        String endpoint = String.format(DOCUMENTAI_ENDPOINT_TEMPLATE, GOOGLE_CLOUD_REGION);
        return DocumentProcessorServiceSettings.newBuilder()
                .setCredentialsProvider(FixedCredentialsProvider.create(creds))
                .setEndpoint(endpoint)
                .build();
    }

    /**
     * Builds the fully-qualified processor resource name for Document AI,
     * which identifies the specific Document AI configuration to use.
     *
     * @return The unique Document AI processor name.
     */
    private String buildProcessorName() {
        return ProcessorName.of(PROJECT_ID, GOOGLE_CLOUD_REGION, PROCESSOR_ID).toString();
    }

    /**
     * Extracts Entities from all of the documents in a given
     * Google Cloud Storage bucket.
     *
     * @param storage       GCS client
     * @param docAi         Document AI client
     * @param writer        CSVWriter
     * @param processorName processor resource name
     */
    private void processAllDocuments(Storage storage,
            DocumentProcessorServiceClient docAiClient,
            String processorName) {

        for (Blob blob : storage.list(INPUT_FILES_BUCKET_NAME,
                Storage.BlobListOption.prefix(INPUT_FILES_DIRECTORY))
                .iterateAll()) {

            processSingleDocument(blob, docAiClient, processorName);
        }
    }

    /**
     * Process a single Document (which is a response from the
     * DocumentAI OCR process.
     *
     * Each Document has a set of lines (which read from the left of the
     * document to the right), analogous to lines of text on a printed
     * page. However these lines may not be contiguous across the page,
     * and may be in text boxes, or tables,
     * etc.
     *
     * The line then has a Layout, and the Layout has a TextAnchor, which is
     * Document AI's way of handling the fact that the line of text may
     * actually be placed in boxes or tables, etc.
     *
     * The TextAnchor has a list of segments, which are positional across
     * the anchor - the positions being the index of a segment within the
     * entire text of the Document.
     *
     * @param blob          The blob representing a file on Google Cloud Storage.
     * @param docAi         The Document AI client.
     * @param writer        The CSVWriter to produce output.
     * @param processorName The DocumentAI Processor Name.
     */
    private void processSingleDocument(Blob blob,
            DocumentProcessorServiceClient docAiClient,
            String processorName) {

        String name = blob.getName();
        if (!isSupportedExtension(name)) {
            logger.info("Unsupported extension for file {}", name);
            return;
        }

        String gcsUri = "gs://" + INPUT_FILES_BUCKET_NAME + '/' + name;
        logger.info("Processing {}", gcsUri);

        // The RawDocument is input to the DocumentAI processor
        RawDocument rawDoc = RawDocument.newBuilder()
                .setContent(ByteString.copyFrom(blob.getContent()))
                .setMimeType(getMimeType(name))
                .build();

        // The ProcessResponse is what DocumentAI sends back
        ProcessResponse resp = docAiClient.processDocument(
                ProcessRequest.newBuilder()
                        .setName(processorName)
                        .setRawDocument(rawDoc)
                        .build());

        // Get all of the lines in the document (the OCR text and confidence)
        List<LineData> lines = extractLinesFromDocument(resp.getDocument());

        // Extract the fields in he lines of text
        Map<String, Entity> fields = extractFields(lines);

        List<String> row = new ArrayList<>();
        row.add(gcsUri);
    }

    /**
     * Confirms that the file extension is supported for OCR.
     *
     * @param name the name of the file.
     * @return true if supported, false if not supported or if name is null.
     */
    private boolean isSupportedExtension(String name) {
        if (name == null) {
            return false;
        }

        List<String> supportedExtensions = List.of(".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".tif");
        for (String ext : supportedExtensions) {
            if (name.toLowerCase().endsWith(ext)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Determines MIME type from filename extension.
     *
     * @param fn The file name.
     * @return The Mime type for the file.
     */
    private String getMimeType(String fn) {
        String ext = fn.substring(fn.lastIndexOf('.') + 1).toLowerCase();
        return MimeType.fromExtension(ext).toString();
    }

    /**
     * Extracts lines of text from a Document AI processing response, and the
     * confidence that Document AI provides for that line.
     *
     * @param doc the Document AI Document which represents an OCR response.
     * @return list of LineData objects (which is the text for a line and the
     *         confidence in the detection of that line).
     */
    private List<LineData> extractLinesFromDocument(Document doc) {
        List<LineData> lines = new ArrayList<>();
        String fullText = doc.getText();

        for (Document.Page page : doc.getPagesList()) {
            for (Document.Page.Line line : page.getLinesList()) {
                String text = extractTextFromDocumentAiLine(line.getLayout().getTextAnchor(), fullText);
                if (!text.isBlank()) {
                    lines.add(new LineData(text, line.getLayout().getConfidence()));
                }
            }
        }
        return lines;
    }

    /**
     * Reconstructs text from TextAnchor segments. The text from the
     * segments are combined into a single String.
     *
     * @param anchor   The TextAnchor that anchors a line within the full text.
     * @param fullText The full text of the entire document.
     * @return The text that each segment in a line contains.
     */
    private String extractTextFromDocumentAiLine(Document.TextAnchor anchor, String fullText) {
        StringBuilder sb = new StringBuilder();
        for (Document.TextAnchor.TextSegment seg : anchor.getTextSegmentsList()) {
            int start = (int) seg.getStartIndex();
            int end = (int) seg.getEndIndex();
            sb.append(fullText, Math.max(0, start), Math.min(fullText.length(), end));

            if(end < fullText.length() && fullText.charAt(end) == '.') {
                sb.append('.');
            }
        }
        return sb.toString().trim();
    }

    /**
     * Look over a set of lines of text from a document for known labels
     * and extract the values for them. To extract a value for a label, we look
     * ahead in the document.
     *
     * For example, we want to know about the entity "Meter Number",
     * which can be labelled "meter", "meter number", "meter no", "meter #". If
     * we find that label, we then seek ahead in the document to find the value
     * (since it may) be next to the label or some number of blank items ahead.
     *
     *
     * @param lines
     * @return
     */
    private Map<String, Entity> extractFields(List<LineData> lines) {
        Map<String, Entity> found = new HashMap<>();
        HEADER_ORDER.forEach(k -> found.put(k, new Entity("", 0, "", "", 0)));

        int i = 0;
        for (LineData line : lines) {
            String originalText = line.getText();
            String lineText = originalText.toLowerCase();
            float confidence = line.getConfidence();

            // Match known labels to find label/text pairs
            if (lineText != null) {
                for (String knownLabel : KNOWN_LABELS.keySet()) {

                    // Iterate the labels that we know about
                    Entity existing = found.get(knownLabel);
                    if (!existing.getEntity().isEmpty()) {
                        // Already set
                        continue;
                    }

                    // Check if the text matches the label
                    Pattern pattern = Pattern.compile(KNOWN_LABELS.get(knownLabel), Pattern.CASE_INSENSITIVE);
                    Matcher m = pattern.matcher(lineText);
                    if (!m.find()) {
                        continue;
                    }

                    // String inputLabel = lineText.trim();
                    String textAfterMatch = originalText.substring(m.end());
                    String value = cleanInlineValue(textAfterMatch);
                    float usedConfidence = confidence;

                    if (!isValueAcceptableForLabel(value, knownLabel)) {
                        value = "";
                        for (int j = i + 1; j < Math.min(i + 6, lines.size()); j++) {
                            LineData next = lines.get(j);
                            if (isValueAcceptableForLabel(next.getText(), knownLabel)) {
                                value = next.getText().trim();
                                usedConfidence = next.getConfidence();
                                break;
                            }
                        }
                    }
                    found.put(knownLabel, new Entity("", 0, knownLabel, value, usedConfidence));
                }
            } else {
                // TODO not needed, remove later
                logger.info("There was no text for the line");
            }
            i++;
        }
        return found;
    }

    /**
     * Confirm whether a given value is suitable for a given label.
     *
     * @param value The value for a label.
     * @param label The label.
     * @return True if the value is a suitable value, false otherwise.
     *         TODO: Implement a more extensible approach. Creating known entities
     *         as instances of Entity, with specific validators for each Entity,
     *         perhaps.
     */
    private boolean isValueAcceptableForLabel(String value, String label) {
        String clean = value.strip();
        String low = clean.toLowerCase();

        if (clean.isEmpty() || VALUES_LIKE_NONE.contains(low) || looksLikeLabel(clean)) {
            return false;
        }
        if (TEXT_FIELDS.contains(label)) {
            return true;
        }

        // Remove non-digits
        String digitsOnly = clean.replaceAll("\\D", "");

        if ("meter_number".equals(label)) {
            if (METER_SKIP_WORDS.stream().anyMatch(clean::contains))
                return false;
            return PURE_DIGITS.matcher(clean).matches() && digitsOnly.length() >= 1;
        }
        if ("customer_account".equals(label)) {
            return digitsOnly.length() >= 5;
        }
        return clean.length() >= 2;
    }

    /**
     * Confirm whether a given piece of text looks like a label
     * (as opposed to a value).
     *
     * @param txt The text to assess.
     * @return Whether or not the given text looks like a label.
     */
    private boolean looksLikeLabel(String txt) {
        String low = txt.toLowerCase().strip();
        if (low.endsWith(":") || low.endsWith(";")) {
            return true;
        }
        return KNOWN_LABELS.values().stream()
                .anyMatch(p -> Pattern.compile(p, Pattern.CASE_INSENSITIVE).matcher(low).find());
    }

    /**
     * Drop leading punctuation & obvious label words like 'number'.
     *
     * @param val The text to clean.
     * @return The text without non-text characters or numbering suffixes.
     */
    private String cleanInlineValue(String val) {
        String v = val.replaceAll("^[ :\\.\\-]+", "").strip();
        return v.matches("(?i)^(number|no\\.?)$") ? "" : v;
    }

    /**
     * Conver
     *
     * @param fd
     * @return
     */
    private String[] formatField(FieldData fd) {
        if (fd == null)
            return new String[] { "", "", "" };
        String conf = fd.getConfidence() == null ? "" : String.format(Locale.US, "%.2f", fd.getConfidence());
        return new String[] { fd.getLabel(), fd.getValue(), conf };
    }

    /* ─────────────────────────── inner types ──────────────────────────── */

    /** Light wrapper around a single OCR line plus its confidence score. */
    private static final class LineData {
        private final String text;
        private final float confidence;

        LineData(String text, float confidence) {
            this.text = text;
            this.confidence = confidence;
        }

        public String getText() {
            return text;
        }

        public float getConfidence() {
            return confidence;
        }
    }

    /** Holds one field's label, extracted value and confidence. */
    private static final class FieldData {
        private final String label;
        private final String value;
        private final Float confidence;

        FieldData(String label, String value, Float confidence) {
            this.label = label;
            this.value = value;
            this.confidence = confidence;
        }

        public String getLabel() {
            return label;
        }

        public String getValue() {
            return value;
        }

        public Float getConfidence() {
            return confidence;
        }
    }

    /** Enum to handle MIME type mapping from file extensions */
    private enum MimeType {
        PNG("image/png"),
        JPG("image/jpeg"),
        JPEG("image/jpeg"),
        PDF("application/pdf"),
        TIF("image/tiff"),
        TIFF("image/tiff");

        private final String mimeType;

        MimeType(String mimeType) {
            this.mimeType = mimeType;
        }

        public static MimeType fromExtension(String ext) {
            try {
                return valueOf(ext.toUpperCase());
            } catch (IllegalArgumentException e) {
                return PDF; // default fallback
            }
        }

        @Override
        public String toString() {
            return mimeType;
        }
    }
}