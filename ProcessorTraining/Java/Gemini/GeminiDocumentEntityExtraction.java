package com.moniepoint.dvs.processor.entities;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

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
 */

@Service
public class GeminiDocumentEntityExtraction {
    private final ObjectMapper mapper = new ObjectMapper();

    private final Storage storage;
    private final GenerativeModel model;
    private final CsvOutputWriter csv;

    private static final Set<String> SUPPORTED =
            Set.of(".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff");

    private static final String PROMPT = String.join("\n", List.of(
            "You are a document-understanding assistant.",
            "Extract the following fields and output ONLY a JSON array of objects:",
            "- Supply Address", "- Service Address", "- Customer Name", "- Period",
            "- Meter Number", "- Meter #", "- Meter Type", "- Transaction Date",
            "- Address", "- Bill Month", "- Customer Account", "- providerAcronym",
            "Each object must have: 'entity', 'value', 'confidence'.",
            "If a field is missing, omit it. DO NOT output any extra text. Confidence must be evaluated per confidence for field name correctly",
            "identified, and per field label."));

    /**
     * Constructs an extractor with shared dependencies for GCS, Gemini, and CSV output.
     *
     * @param storage Google Cloud Storage client
     * @param model   Generative AI model (Gemini)
     * @param csv     Writer for outputting structured CSV records
     */
    @Autowired
    public GeminiDocumentEntityExtraction(Storage storage,
                                          GenerativeModel model,
                                          CsvOutputWriter csv) {
        this.storage = storage;
        this.model = model;
        this.csv = csv;
    }

    /**
     * Executes the document-ingestion → entity-extraction → CSV-persistence pipeline.
     *
     * @throws IOException if any error occurs reading blobs or writing CSV
     */
    public void run() throws IOException {
        csv.writeHeader();
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
     * - Asynchronous processing, meaning multiple threads run in parallel.
     *
     *
     */


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
}
