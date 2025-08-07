package com.moniepoint.dvs.processor.entities;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.apache.commons.lang3.exception.UncheckedException;
    /**
     * Utility to read the JSON file created by GeminiDocumentEnity Extraction
     * into list of entity records
     *
     * @author adrian@adg.io
     * @apiNote Document Verification Service
     */
public class JsonEntityParser {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * Parses the given JSON string (which must be an array of Entity Objects)
     * and returns a List of Entity
     *
     * @param jsonContent raw JSON array
     * @return List of GeminiDocumentEntityExtraction.Entity
     * @throws UncheckedIOException if the JSON is invalid
     */
    public static List<GeminiDocumentEntityExtraction.Entity> parseEntities(String jsonContent) throws IOException {
        try {
            return MAPPER.readValue(
                jsonContent,
                new TypeReference<List<GeminiDocumentEntityExtraction.Entity>>() {}
            );
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to parse Entity JSON", e);
        }

    }
}
