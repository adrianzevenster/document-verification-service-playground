package com.moniepoint.dvs.processor;

/**
 * Represents a single extracted entity record from a document.
 */
public class Entity {
    private final String gcsUri;
    private final int page;
    private final String entity;
    private final String value;
    private final double confidence;

    /**
     * @param gcsUri     URI of the source blob
     * @param page       page number in multi-page documents
     * @param entity     extracted field name
     * @param value      extracted text
     * @param confidence confidence score between 0.0 and 1.0
     */
    public Entity(String gcsUri, int page, String entity, String value, double confidence) {
        this.gcsUri = gcsUri;
        this.page = page;
        this.entity = entity;
        this.value = value;
        this.confidence = confidence;
    }

    public String getGcsUri() { return gcsUri; }
    public int getPage() { return page; }
    public String getEntity() { return entity; }
    public String getValue() { return value; }
    public double getConfidence() { return confidence; }
}
