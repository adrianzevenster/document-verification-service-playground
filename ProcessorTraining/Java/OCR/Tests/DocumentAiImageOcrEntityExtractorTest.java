package com.moniepoint.dvs.processor.entities;

import com.google.cloud.documentai.v1.*;
import com.google.cloud.storage.Blob;
import com.google.protobuf.ByteString;
import com.moniepoint.dvs.component.ConfigurationManager;
import com.moniepoint.dvs.processor.Entity;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DocumentAiImageOcrEntityExtractorTest {
        @Mock
        private ConfigurationManager mockConfigurationManager;
        @Mock
        private DocumentProcessorServiceClient mockDocAiClient;
        @Mock
        private Blob mockBlob;

        @Captor
        private ArgumentCaptor<ProcessRequest> processRequestCaptor;

        private DocumentAiImageOcrEntityExtractor extractor;

        // Test constants for configuration
        private static final String TEST_PROJECT_ID = "test-project";
        private static final String TEST_REGION = "us-test1";
        private static final String TEST_PROCESSOR_ID = "test-processor";
        private static final String TEST_BUCKET_NAME = "test-bucket";
        private static final String TEST_DIRECTORY = "test-dir/";
        private static final String TEST_SA_KEY = "{\"type\": \"service_account\"}"; // Dummy JSON

        // Helper to invoke private methods
        private <T> T invokePrivateMethod(Object instance, String methodName, Class<?>[] parameterTypes,
                        Object[] parameters) throws Exception {
                Method method = instance.getClass().getDeclaredMethod(methodName, parameterTypes);
                method.setAccessible(true);
                // noinspection unchecked
                return (T) method.invoke(instance, parameters);
        }

        @BeforeEach
        void setUp() {
                when(mockConfigurationManager.getConfiguration("ocr.project.id")).thenReturn(TEST_PROJECT_ID);
                when(mockConfigurationManager.getConfiguration("ocr.cloud.region")).thenReturn(TEST_REGION);
                when(mockConfigurationManager.getConfiguration("ocr.processor.id")).thenReturn(TEST_PROCESSOR_ID);
                when(mockConfigurationManager.getConfiguration("ocr.input.documents.bucket"))
                                .thenReturn(TEST_BUCKET_NAME);
                when(mockConfigurationManager.getConfiguration("ocr.input.documents.directory"))
                                .thenReturn(TEST_DIRECTORY);
                when(mockConfigurationManager.getConfiguration("ocr.serviceaccount.key")).thenReturn(TEST_SA_KEY);

                extractor = new DocumentAiImageOcrEntityExtractor(mockConfigurationManager);
        }

        @Nested
        class IsSupportedExtensionTests {
                static Stream<Arguments> supportedExtensionsProvider() {
                        return Stream.of(
                                        Arguments.of("document.pdf", true),
                                        Arguments.of("image.PNG", true),
                                        Arguments.of("photo.jpg", true),
                                        Arguments.of("archive.jpeg", true),
                                        Arguments.of("scan.tiff", true),
                                        Arguments.of("multipage.tif", true),
                                        Arguments.of("textfile.txt", false),
                                        Arguments.of("archive.zip", false),
                                        Arguments.of("image.PDF", true), // Case insensitivity of filename
                                        Arguments.of("nodotextension", false),
                                        Arguments.of(null, false));
                }

                @ParameterizedTest
                @MethodSource("supportedExtensionsProvider")
                void testIsSupportedExtension(String fileName, boolean expected) throws Exception {
                        boolean actual = invokePrivateMethod(extractor, "isSupportedExtension",
                                        new Class<?>[] { String.class }, new Object[] { fileName });
                        assertEquals(expected, actual);
                }
        }

        @Nested
        class GetMimeTypeTests {
                static Stream<Arguments> mimeTypeProvider() {
                        return Stream.of(
                                        Arguments.of("file.pdf", "application/pdf"),
                                        Arguments.of("image.png", "image/png"),
                                        Arguments.of("photo.jpg", "image/jpeg"),
                                        Arguments.of("archive.jpeg", "image/jpeg"),
                                        Arguments.of("scan.tiff", "image/tiff"),
                                        Arguments.of("multi.tif", "image/tiff"),
                                        // Test internal MimeType enum's fallback for unknown extensions
                                        Arguments.of("unknown.ext", "application/pdf"), // Falls back to PDF as per

                                        Arguments.of("file.PDF", "application/pdf"));
                }

                @ParameterizedTest
                @MethodSource("mimeTypeProvider")
                void testGetMimeType(String fileName, String expectedMimeType) throws Exception {
                        String actual = invokePrivateMethod(extractor, "getMimeType", new Class<?>[] { String.class },
                                        new Object[] { fileName });
                        assertEquals(expectedMimeType, actual);
                }

                @Test
                void internalMimeTypeEnum_fromExtension_unknown() throws Exception {
                        // Accessing the private enum MimeType and its static method via reflection
                        Class<?> mimeTypeEnum = Class.forName(
                                        "com.moniepoint.dvs.processor.entities.DocumentAiImageOcrEntityExtractor$MimeType");
                        Method fromExtensionMethod = mimeTypeEnum.getDeclaredMethod("fromExtension", String.class);
                        fromExtensionMethod.setAccessible(true);

                        Object resultEnum = fromExtensionMethod.invoke(null, "xyz"); // Call static method
                        assertEquals("application/pdf", resultEnum.toString()); // Default fallback in SUT's MimeType
                }
        }

        @Test
        void extractTextFromDocumentAiLine_reconstructsText() throws Exception {
                String fullText = "This is the full document text.";
                Document.TextAnchor anchor = Document.TextAnchor.newBuilder()
                                .addTextSegments(Document.TextAnchor.TextSegment.newBuilder().setStartIndex(0)
                                                .setEndIndex(4)) // "This"
                                .addTextSegments(Document.TextAnchor.TextSegment.newBuilder().setStartIndex(4)
                                                .setEndIndex(8)) // " is " (includes leading space)
                                .build();

                String expectedText = "This is"; // SUT trims the result
                String actualText = invokePrivateMethod(extractor, "extractTextFromDocumentAiLine",
                                new Class<?>[] { Document.TextAnchor.class, String.class },
                                new Object[] { anchor, fullText });
                assertEquals(expectedText, actualText);

                // Test with empty segments
                Document.TextAnchor emptyAnchor = Document.TextAnchor.newBuilder().build();
                String actualEmpty = invokePrivateMethod(extractor, "extractTextFromDocumentAiLine",
                                new Class<?>[] { Document.TextAnchor.class, String.class },
                                new Object[] { emptyAnchor, fullText });
                assertEquals("", actualEmpty);
        }

        @Test
        void extractLinesFromDocument_extractsLineData() throws Exception {
                String fullText = "First line.\nSecond line, with confidence.";
                Document.Page.Line line1 = Document.Page.Line.newBuilder()
                                .setLayout(Document.Page.Layout.newBuilder()
                                                .setTextAnchor(Document.TextAnchor.newBuilder()
                                                                .addTextSegments(Document.TextAnchor.TextSegment
                                                                                .newBuilder().setStartIndex(0)
                                                                                .setEndIndex(11))) // "First line."
                                                .setConfidence(0.95f))
                                .build();
                Document.Page.Line line2 = Document.Page.Line.newBuilder()
                                .setLayout(Document.Page.Layout.newBuilder()
                                                .setTextAnchor(Document.TextAnchor.newBuilder()
                                                                .addTextSegments(Document.TextAnchor.TextSegment
                                                                                .newBuilder().setStartIndex(12)
                                                                                .setEndIndex(40))) // "Second line, with
                                                                                                   // confidence."
                                                .setConfidence(0.88f))
                                .build();

                Document.Page page = Document.Page.newBuilder().addLines(line1).addLines(line2).build();
                Document doc = Document.newBuilder().setText(fullText).addPages(page).build();

                List<Object> lineDataList = invokePrivateMethod(extractor, "extractLinesFromDocument",
                                new Class<?>[] { Document.class },
                                new Object[] { doc });

                assertEquals(2, lineDataList.size());

                Object lineData1 = lineDataList.get(0);
                assertEquals("First line.", lineData1.getClass().getMethod("getText").invoke(lineData1));
                assertEquals(0.95f, (Float) lineData1.getClass().getMethod("getConfidence").invoke(lineData1), 0.001);

                Object lineData2 = lineDataList.get(1);
                assertEquals("Second line, with confidence.",
                                lineData2.getClass().getMethod("getText").invoke(lineData2));
                assertEquals(0.88f, (Float) lineData2.getClass().getMethod("getConfidence").invoke(lineData2), 0.001);
        }

        @Nested
        class IsValueAcceptableForLabelTests {
                // String value, String label, boolean expected
                static Stream<Arguments> valueAcceptabilityProvider() {
                        return Stream.of(
                                        // Basic empty/NA checks
                                        Arguments.of("", "name", false),
                                        Arguments.of("  ", "name", false),
                                        Arguments.of("N/A", "name", false),
                                        Arguments.of("None", "period", false),
                                        Arguments.of("Meter Number:", "meter_number", false), // Looks like a label

                                        // Text fields
                                        Arguments.of("John Doe", "name", true),
                                        Arguments.of("123 Main St", "address", true),

                                        // Meter number
                                        Arguments.of("12345", "meter_number", true),
                                        Arguments.of("ABCDE", "meter_number", false), // Not pure digits
                                        Arguments.of("old 123", "meter_number", false), // Contains skip word
                                        Arguments.of("account 123", "meter_number", false),
                                        Arguments.of("", "meter_number", false),

                                        // Customer account
                                        Arguments.of("987654321", "customer_account", true),
                                        Arguments.of("98765", "customer_account", true),
                                        Arguments.of("1234", "customer_account", false), // Too short
                                        Arguments.of("ACC12345", "customer_account", true), // Non-digits are removed

                                        // Generic
                                        Arguments.of("Val", "period", true),
                                        Arguments.of("V", "period", false) // Too short
                        );
                }

                @ParameterizedTest
                @MethodSource("valueAcceptabilityProvider")
                void testIsValueAcceptableForLabel(String value, String label, boolean expected) throws Exception {
                        boolean actual = invokePrivateMethod(extractor, "isValueAcceptableForLabel",
                                        new Class<?>[] { String.class, String.class },
                                        new Object[] { value, label });
                        assertEquals(expected, actual, "Value '" + value + "' for label '" + label + "'");
                }
        }

        @Nested
        class LooksLikeLabelTests {
                static Stream<Arguments> labelLikenessProvider() {
                        return Stream.of(
                                        Arguments.of("Name:", true),
                                        Arguments.of("Address ;", true),
                                        Arguments.of("Supply Address", true), // Matches a known pattern
                                        Arguments.of("Meter Number", true),
                                        Arguments.of("John Doe", false),
                                        Arguments.of("12345", false),
                                        Arguments.of("Some random text", false));
                }

                @ParameterizedTest
                @MethodSource("labelLikenessProvider")
                void testLooksLikeLabel(String text, boolean expected) throws Exception {
                        boolean actual = invokePrivateMethod(extractor, "looksLikeLabel",
                                        new Class<?>[] { String.class },
                                        new Object[] { text });
                        assertEquals(expected, actual, "Text '" + text + "'");
                }
        }

        @Nested
        class CleanInlineValueTests {
                static Stream<Arguments> inlineValueProvider() {
                        return Stream.of(
                                        Arguments.of(" :.- Value ", "Value"),
                                        Arguments.of("Value", "Value"),
                                        Arguments.of("Number", ""), // "number" is a keyword to remove
                                        Arguments.of("No. ", ""), // "no." is a keyword to remove
                                        Arguments.of("Value number one", "Value number one") // "number" not at start
                                                                                               // of cleaned string
                        );
                }

                @ParameterizedTest
                @MethodSource("inlineValueProvider")
                void testCleanInlineValue(String value, String expected) throws Exception {
                        String actual = invokePrivateMethod(extractor, "cleanInlineValue",
                                        new Class<?>[] { String.class },
                                        new Object[] { value });

                        String exp = String.format("[%s] input and [%s] expected", value, expected);
                        String act = String.format("[%s] input and [%s] expected", value, actual);

                        assertEquals(exp, act);
                }
        }

        @Test
        void formatField_formatsCorrectly() throws Exception {
                // Need to instantiate the private inner class FieldData via reflection or make
                // it accessible
                Class<?> fieldDataClass = Class.forName(
                                "com.moniepoint.dvs.processor.entities.DocumentAiImageOcrEntityExtractor$FieldData");
                Object fieldDataInstance = fieldDataClass
                                .getDeclaredConstructor(String.class, String.class, Float.class)
                                .newInstance("Label1", "Value1", 0.987f);

                String[] result = invokePrivateMethod(extractor, "formatField",
                                new Class<?>[] { fieldDataClass },
                                new Object[] { fieldDataInstance });
                assertArrayEquals(new String[] { "Label1", "Value1", "0.99" }, result);

                Object nullConfidenceInstance = fieldDataClass
                                .getDeclaredConstructor(String.class, String.class, Float.class)
                                .newInstance("Label2", "Value2", null);
                result = invokePrivateMethod(extractor, "formatField",
                                new Class<?>[] { fieldDataClass },
                                new Object[] { nullConfidenceInstance });
                assertArrayEquals(new String[] { "Label2", "Value2", "" }, result);

                result = invokePrivateMethod(extractor, "formatField",
                                new Class<?>[] { fieldDataClass },
                                new Object[] { null });
                assertArrayEquals(new String[] { "", "", "" }, result);
        }

        @Test
        void extractFields_identifiesEntities() throws Exception {
                // Create LineData instances (requires reflection for private inner class)
                Class<?> lineDataClass = Class.forName(
                                "com.moniepoint.dvs.processor.entities.DocumentAiImageOcrEntityExtractor$LineData");
                Object line1 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("Customer Name: John Doe", 0.95f);
                Object line2 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("Meter Number", 0.9f); // Label
                Object line3 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("123456789", 0.85f); // Value for meter number
                Object line4 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("Period: Jan 2023", 0.92f);
                Object line5 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("Address: N/A", 0.8f); // N/A should be skipped for value
                Object line6 = lineDataClass.getDeclaredConstructor(String.class, float.class)
                                .newInstance("123 Main St", 0.8f); // Value for address (if N/A was skipped)

                List<Object> lines = List.of(line1, line2, line3, line4, line5, line6);

                Map<String, Entity> actualFields = invokePrivateMethod(extractor, "extractFields",
                                new Class<?>[] { List.class },
                                new Object[] { lines });

                assertNotNull(actualFields.get("name"));
                assertEquals("John Doe", actualFields.get("name").getValue());
                assertEquals(0.95f, actualFields.get("name").getConfidence(), 0.001);

                assertNotNull(actualFields.get("meter_number"));
                assertEquals("123456789", actualFields.get("meter_number").getValue());
                assertEquals(0.85f, actualFields.get("meter_number").getConfidence(), 0.001);

                assertNotNull(actualFields.get("period"));
                assertEquals("Jan 2023", actualFields.get("period").getValue());
                assertEquals(0.92f, actualFields.get("period").getConfidence(), 0.001);

                // Address is tricky because "Address: N/A" might be rejected, then "123 Main
                // St" picked up.
                // The current logic for "Address: N/A" -> isValueAcceptableForLabel("N/A",
                // "address") -> false
                // Then it looks ahead.
                assertNotNull(actualFields.get("address"));
                assertEquals("123 Main St", actualFields.get("address").getValue());
                assertEquals(0.8f, actualFields.get("address").getConfidence(), 0.001);

                // Check that all HEADER_ORDER keys are present, even if empty
                assertTrue(actualFields.containsKey("supply_address"));
                assertTrue(actualFields.containsKey("bill_month"));
        }

        @Test
        void processSingleDocument_supportedFile() throws Exception {
                String fileName = "supported_doc.pdf";
                byte[] fileContent = "pdf content".getBytes();
                String expectedGcsUri = "gs://" + TEST_BUCKET_NAME + "/" + fileName;
                String expectedProcessorName = ProcessorName.of(TEST_PROJECT_ID, TEST_REGION, TEST_PROCESSOR_ID)
                                .toString();

                when(mockBlob.getName()).thenReturn(fileName);
                when(mockBlob.getContent()).thenReturn(fileContent);

                // Mock Document AI response
                ProcessResponse mockResponse = ProcessResponse.newBuilder()
                                .setDocument(Document.newBuilder().setText("Extracted text from PDF.").build())
                                .build();
                when(mockDocAiClient.processDocument(any(ProcessRequest.class))).thenReturn(mockResponse);

                // Call the private method using reflection
                // Note: This method in SUT doesn't use a CSVWriter and its output (row) is not
                // used.
                // We are testing interactions and request building.
                invokePrivateMethod(extractor, "processSingleDocument",
                                new Class<?>[] { Blob.class, DocumentProcessorServiceClient.class, String.class },
                                new Object[] { mockBlob, mockDocAiClient, expectedProcessorName });

                verify(mockDocAiClient).processDocument(processRequestCaptor.capture());
                ProcessRequest actualRequest = processRequestCaptor.getValue();

                assertEquals(expectedProcessorName, actualRequest.getName());
                assertEquals("application/pdf", actualRequest.getRawDocument().getMimeType());
                assertEquals(ByteString.copyFrom(fileContent), actualRequest.getRawDocument().getContent());

                // Further verification could involve spying on `extractor` to check calls to
                // `extractLinesFromDocument` and `extractFields`, but that adds complexity.
                // Knowing `processDocument` was called with correct params is a good step.
        }

        @Test
        void processSingleDocument_unsupportedFile() throws Exception {
                String fileName = "unsupported_doc.txt";
                String expectedProcessorName = "processorName"; // Doesn't matter as it won't be called

                when(mockBlob.getName()).thenReturn(fileName);
                // No need to mock getContent as it should return early

                invokePrivateMethod(extractor, "processSingleDocument",
                                new Class<?>[] { Blob.class, DocumentProcessorServiceClient.class, String.class },
                                new Object[] { mockBlob, mockDocAiClient, expectedProcessorName });

                verify(mockDocAiClient, never()).processDocument(any(ProcessRequest.class));
        }
}
