package com.moniepoint.dvs.processor.entities;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import com.google.cloud.vertexai.api.*;
import com.google.cloud.vertexai.generativeai.GenerativeModel;
import com.moniepoint.dvs.processor.entities.GeminiDocumentEntityExtraction;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.graphics.state.RenderingMode;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.lang.reflect.Method;
import java.util.List;

/**
 * Unit-tests for {@link GeminiDocumentEntityExtraction}.
 */

@ExtendWith(MockitoExtension.class)
class GeminiDocumentEntityExtractionTest {

    /* ── collaborators ────────────────────────────────────────────── */
    @Mock Storage storage;
    @Mock GenerativeModel model;
    @Mock GeminiDocumentEntityExtraction.CsvOutputWriter csv;

    /** Deep-stub lets us chain calls like response.getCandidates(0).getContent() … */
    @Mock(answer = Answers.RETURNS_DEEP_STUBS)
    GenerateContentResponse response;

    GeminiDocumentEntityExtraction target;

    @BeforeEach
    void init() {
        target = new GeminiDocumentEntityExtraction(storage, model, csv);
    }

    /* ── analysePage ──────────────────────────────────────────────── */

    @Test
    void analysePage_returnsEntities_whenPlainJson() throws Exception {
        mockModel("""
            [{"entity":"Meter Number","value":"123","confidence":0.91}]
            """);

        var out = invokeAnalysePage("png".getBytes());

        assertThat(out).singleElement()
                       .satisfies(e -> {
                           assertThat(e.entity()).isEqualTo("Meter Number");
                           assertThat(e.value()).isEqualTo("123");
                           assertThat(e.confidence()).isEqualTo(0.91f);
                       });
    }

    @Test
    void analysePage_stripsMarkdownFences() throws Exception {
        mockModel("""
            ```json
            [{"entity":"Customer Name","value":"Jane","confidence":0.8}]
            ```
            """);

        var out = invokeAnalysePage("img".getBytes());

        assertThat(out).singleElement()
                       .extracting(GeminiDocumentEntityExtraction.Entity::value)
                       .isEqualTo("Jane");
    }

    /* ── run() end-to-end (mocked IO) ─────────────────────────────── */

    @Test
    void run_processesSupportedBlobs_andWritesCsvRows() throws Exception {
        // one supported .png blob and a directory placeholder
        Blob png = mock(Blob.class);
        when(png.getName()).thenReturn("training-documents/sample.png");
        when(png.getContent()).thenReturn("img".getBytes());

        Blob dir = mock(Blob.class);
        when(dir.getName()).thenReturn("training-documents/");

        Page<Blob> page = mock(Page.class);
        when(page.iterateAll()).thenReturn(List.of(png, dir));
        when(storage.list(any(), any())).thenReturn(page);

        mockModel("""
            [{"entity":"Meter Number","value":"42","confidence":0.6}]
            """);

        target.run();

        // header + 1 data row in order
        InOrder io = inOrder(csv);
        io.verify(csv).writeHeader();
        io.verify(csv).write(any(GeminiDocumentEntityExtraction.Entity.class));
        io.verifyNoMoreInteractions();
    }

    /* ── pdfToPngPages ────────────────────────────────────────────── */

    @Test
    void pdfToPngPages_returnsSinglePage_forOnePagePdf() throws Exception {
        byte[] pdf  = createOnePagePdf("hello world");
        var   pages = invokePdfToPngPages(pdf);

        assertThat(pages).hasSize(1);
        assertThat(pages.getFirst().length).isGreaterThan(100);
    }

    /* ── helpers ─────────────────────────────────────────────────── */

        /**
         * Stubs {@code model.generateContent(…)} so it returns our deep-stubbed
         * {@code response}. Declares {@code IOException} so the compiler is satisfied.
         */
    private void mockModel(String json) throws IOException {
        Candidate cand  = mock(Candidate.class);
        Content content = mock(Content.class);
        Part part       = mock(Part.class);

        // method call still type-checked, so declare the checked exception
        doReturn(response).when(model).generateContent(any(Content.class));

        when(response.getCandidates(0)).thenReturn(cand);
        when(cand.getContent()).thenReturn(content);
        when(content.getParts(0)).thenReturn(part);
        when(part.getText()).thenReturn(json);
    }

    @SuppressWarnings("unchecked")
    private List<GeminiDocumentEntityExtraction.Entity> invokeAnalysePage(byte[] png)
            throws Exception {

        Method m = GeminiDocumentEntityExtraction.class
                .getDeclaredMethod("analysePage", byte[].class, String.class, int.class);
        m.setAccessible(true);
        return (List<GeminiDocumentEntityExtraction.Entity>)
                m.invoke(target, png, "gs://bucket/doc.pdf", 1);
    }

    @SuppressWarnings("unchecked")
    private List<byte[]> invokePdfToPngPages(byte[] pdf) throws Exception {
        Method m = GeminiDocumentEntityExtraction.class
                .getDeclaredMethod("pdfToPngPages", byte[].class);
        m.setAccessible(true);
        return (List<byte[]>) m.invoke(target, (Object) pdf);
    }

    /** Creates a very small single-page PDF entirely in memory. */
    private static byte[] createOnePagePdf(String text) throws IOException {
        try (PDDocument doc = new PDDocument()) {
            PDPage page = new PDPage(PDRectangle.A4);
            doc.addPage(page);

            try (PDPageContentStream cs = new PDPageContentStream(doc, page)) {
                cs.beginText();
                cs.setFont(PDType1Font.HELVETICA_BOLD, 12);
                cs.setRenderingMode(RenderingMode.FILL);
                cs.newLineAtOffset(50, 750);
                cs.showText(text);
                cs.endText();
            }

            try (ByteArrayOutputStream os = new ByteArrayOutputStream()) {
                doc.save(os);
                return os.toByteArray();
            }
        }
    }
}
