package com.moniepoint.dvs.processor.entities;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.google.api.gax.paging.Page;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ServiceAccountCredentials;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.vertexai.VertexAI;
import com.google.cloud.vertexai.api.*;
import com.google.cloud.vertexai.generativeai.GenerativeModel;
import com.moniepoint.dvs.component.ConfigurationManager;
import com.opencsv.CSVWriter;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.*;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Downloads every PDF / image under a GCS bucket/prefix, sends each page to
 * Gemini 2 Flash for entity extraction, and writes the results into a CSV file.
 *
 * <p>This component encapsulates document ingestion, LLM inference, and
 * structured CSV persistence.</p>
 *
 * @author adrian@adg.io
 * @apiNote Document Verification Service
 */
@Component
public class GeminiDocumentEntityExtraction {
    private final ObjectMapper mapper = new ObjectMapper();

    private final Storage storage;
    private final GenerativeModel model;
    private final CsvOutputWriter csv;
    private final JsonOutputWriter json;

    private static final Set<String> SUPPORTED =
            Set.of(".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff");

    private static final String PROMPT = String.join("\n", List.of(
            "You are a document-understanding assistant.",
            "Extract the following fields and output ONLY a JSON array of objects:",
            "- Supply Address", "- Service Address", "- Customer Name", "- Period",
            "- Meter Number", "- Meter #", "- Meter Type", "- Transaction Date",
            "- Address", "- Bill Month", "- Customer Account", "- providerAcronym",
            "Each object must have: 'entity', 'value', 'confidence'.",
            "If a field is missing, omit it. DO NOT output any extra text." ,
            " Confidence must be evaluated per confidence for field name correctly",
            "identified, and per field label. Output needs to be a json object array"));

    /**
     * Constructs an extractor with shared dependencies for GCS, Gemini, and CSV output.
     *
     * @param storage Google Cloud Storage client
     * @param model   Generative AI model (Gemini)
     * @param csv     Writer for outputting structured CSV records
     * @param json    Writer for outputting structured JSON records
     */
    public GeminiDocumentEntityExtraction(Storage storage,
                                          GenerativeModel model,
                                          CsvOutputWriter csv,
                                          JsonOutputWriter json) {
        this.storage = storage;
        this.model = model;
        this.csv = csv;
        this.json = json;
    }

    /**
     * Executes the document-ingestion → entity-extraction → CSV-persistence pipeline.
     *
     * @throws IOException if any error occurs reading blobs or writing CSV
     */
    public void run() throws IOException {
        csv.writeHeader();
        // json has no header

        Page<Blob> blobs = storage.list(System.getProperty("GEMINI_INPUT_BUCKET"),
                Storage.BlobListOption.prefix(System.getProperty("GEMINI_INPUT_DIR", "")));

        for (Blob blob : blobs.iterateAll()) {
            String name = blob.getName().toLowerCase();
            if (name.endsWith("/") || SUPPORTED.stream().noneMatch(name::endsWith)) continue;
            String gcsUri = "gs://" + System.getProperty("GEMINI_INPUT_BUCKET") + '/' + blob.getName();
            byte[] content = blob.getContent();
            List<byte[]> pages = name.endsWith(".pdf") ? pdfToPngPages(content) : List.of(content);
            for (int i = 0; i < pages.size(); i++) {
                for (Entity e : analysePage(pages.get(i), gcsUri, i + 1)) {
                    csv.write(e);
                    json.write(e);
                }
            }
        }
    }

    /**
     * Analyzes a PNG image using Gemini to extract structured entities.
     *
     * @param pngPage PNG bytes
     * @param uri     Source GCS URI
     * @param pageNo  1-based page index
     * @return List of extracted {@link Entity} records
     * @throws IOException if parsing or Gemini interaction fails
     */
    private List<Entity> analysePage(byte[] pngPage, String uri, int pageNo) throws IOException {
        Part promptPart = Part.newBuilder().setText(PROMPT).build();
        Part imagePart = Part.newBuilder()
                .setInlineData(com.google.cloud.vertexai.api.Blob.newBuilder()
                        .setMimeType("image/png")
                        .setData(com.google.protobuf.ByteString.copyFrom(pngPage))
                        .build())
                .build();

        Content requestContent = Content.newBuilder()
                .addParts(promptPart)
                .addParts(imagePart)
                .build();

        GenerateContentResponse resp = model.generateContent(requestContent);
        String raw = resp.getCandidates(0).getContent().getParts(0).getText().strip();
        if (raw.startsWith("```")) {
            raw = Arrays.stream(raw.split("\n"))
                    .filter(l -> !l.startsWith("```"))
                    .collect(Collectors.joining("\n"));
        }

        List<Map<String, Object>> list = mapper.readValue(raw, new TypeReference<>() {});
        List<Entity> out = new ArrayList<>(list.size());
        for (Map<String, Object> m : list) {
            out.add(new Entity(
                    uri,
                    pageNo,
                    (String) m.get("entity"),
                    (String) m.get("value"),
                    ((Number) m.get("confidence")).floatValue()));
        }
        return out;
    }

    /**
     * Converts each page of a PDF to a 200 DPI PNG image.
     *
     * @param pdf raw PDF bytes
     * @return list of PNG byte arrays
     * @throws IOException if rendering fails
     */
    private List<byte[]> pdfToPngPages(byte[] pdf) throws IOException {
        try (PDDocument doc = PDDocument.load(new ByteArrayInputStream(pdf))) {
            PDFRenderer renderer = new PDFRenderer(doc);
            List<byte[]> pages = new ArrayList<>();
            for (int i = 0; i < doc.getNumberOfPages(); i++) {
                BufferedImage img = renderer.renderImageWithDPI(i, 200);
                try (ByteArrayOutputStream os = new ByteArrayOutputStream()) {
                    ImageIO.write(img, "PNG", os);
                    pages.add(os.toByteArray());
                }
            }
            return pages;
        }
    }

    /**
     * Entrypoint for manual invocation or CLI usage.
     *
     * @param args ignored
     * @throws Exception if initialization or execution fails
     *
     * TODO: Single bucket path (URI) processing
     *  - Concurrent single bucket processing, meaning multiple threads run in parallel.
     *
     *
     */
    public static void main(String[] args) throws Exception {
        ConfigurationManager configManager = new ConfigurationManager();

        String PROJECT_ID = configManager.getConfiguration("gemini.project.id");
        String GOOGLE_CLOUD_REGION = configManager.getConfiguration("gemini.cloud.region");
        String GEMINI_MODEL_NAME = configManager.getConfiguration("gemini.model.name");
        String OUPUT_CSV_FILE_PATH = configManager.getConfiguration("gemini.documents.output.file");
        String GCP_KEY_PATH = configManager.getConfiguration("gemini.serviceaccount.key");
        String INPUT_DOCUMENTS_BUCKET_NAME = configManager.getConfiguration("gemini.input.documents.bucket");
        String INPUT_DOCUEMENTS_FILE_PATH = configManager.getConfiguration("gemini.input.documents.directory");
        String OUTPUT_JSON_FILE_PATH = configManager.getConfiguration("gemini.documents.output.json");

        System.setProperty("GEMINI_INPUT_BUCKET", INPUT_DOCUMENTS_BUCKET_NAME);
        System.setProperty("GEMINI_INPUT_DIR", INPUT_DOCUEMENTS_FILE_PATH);

        GoogleCredentials creds = ServiceAccountCredentials
                .fromStream(new FileInputStream(configManager.getConfiguration("gemini.serviceaccount.key")));

        Storage storage = StorageOptions.newBuilder()
                .setProjectId(PROJECT_ID)
                .setCredentials(creds)
                .build()
                .getService();

        try (
            VertexAI vertexAi = new VertexAI(PROJECT_ID, GOOGLE_CLOUD_REGION, creds);
            CsvOutputWriter csv = new CsvOutputWriter(OUPUT_CSV_FILE_PATH);
            JsonOutputWriter json = new JsonOutputWriter(OUTPUT_JSON_FILE_PATH)
        ) {
            GenerativeModel model = new GenerativeModel(GEMINI_MODEL_NAME, vertexAi);
                new GeminiDocumentEntityExtraction(storage, model, csv, json).run();
        }



        System.out.println("Done → CSV: " + OUPUT_CSV_FILE_PATH
                + ", JSON: " + OUTPUT_JSON_FILE_PATH);
    }

    /**
     * Immutable record that holds the result of entity extraction from a document.
     *
     * @param uri        GCS URI of the document
     * @param page       1-based page index
     * @param entity     Extracted field name
     * @param value      Extracted field value
     * @param confidence Confidence score from the model
     */
    public record Entity(String uri, int page, String entity,
                         String value, Float confidence) { }

    /**
     * Helper class to write entity extraction results to a CSV file.
     */
    public static final class CsvOutputWriter implements AutoCloseable {
        private final CSVWriter csv;

        /**
         * Creates a writer to the specified file.
         * @param file path to CSV file
         * @throws IOException if file cannot be written
         *
         * TODO: write up to database connection
         *
         * JIRA: https://teamapt.atlassian.net/browse/DVSS-191
         * JIRA: https://teamapt.atlassian.net/browse/DVSS-192
         */
        CsvOutputWriter(String file) throws IOException {
            csv = new CSVWriter(new FileWriter(file));
        }

        /**
         * Writes the CSV header.
         */
        void writeHeader() {
            csv.writeNext(new String[] {
                    "gcs_uri", "page", "entity", "value", "confidence"});
        }

        /**
         * Writes a single entity row.
         * @param e entity object
         */
        void write(Entity e) {
            csv.writeNext(new String[] {
                    e.uri(), String.valueOf(e.page()),
                    e.entity(), e.value(),
                    e.confidence() == null ? "" : e.confidence().toString()});
        }

        /**
         * Closes the writer.
         * @throws IOException if closing fails
         *
         */
        @Override
        public void close() throws IOException {
            csv.close();
        }
    }

    // --- JsonOutputWriter class inserted here ---
    /**
     * Helper class to write entity extraction results to a JSON file.
     */
    public static final class JsonOutputWriter implements AutoCloseable {
        private final ObjectMapper mapper = new ObjectMapper();
        private final ObjectWriter writer = mapper.writerWithDefaultPrettyPrinter();
        private final List<Entity> buffer = new ArrayList<>();
        private final File outFile;

        /**
         * Creates a JSON writer to the specified file.
         * @param filePath path to JSON output file
         */
        public JsonOutputWriter(String filePath) {
            this.outFile = new File(filePath);
        }

        /**
         * Buffers one entity for JSON output.
         * @param e entity object
         */
        public void write(Entity e) {
            buffer.add(e);
        }

        /**
         * Dumps all buffered entities as a JSON array when closed.
         * @throws IOException if writing fails
         */
        @Override
        public void close() throws IOException {
            mapper.writeValue(outFile, buffer);
        }
    }
}
