package com.moniepoint.dvs.processor.entities;
/**
 * Mime-type lookup by file extension.
 *
 * @author adrian@adg.io
 * @apiNote document verification solution
 */
public enum MimeType {
    PNG("png", "image/png"),
    JPG("jpg", "image/jpeg"),
    JPEG("jpeg", "image/jpeg"),
    PDF("pdf", "application/pdf"),
    TIFF("tiff", "image/tiff"),
    TIF("tif", "image/tiff"),
    DEFAULT("", "application/octet-stream");

    private final String ext;
    private final String type;

    MimeType(String ext, String type) {
        this.ext = ext;
        this.type = type;
    }

    @Override
    public String toString() {
        return type;
    }

    /**
     * Looks up a MimeType by file extension.
     *
     * @param ext Extension of file
     * @return MimeType enum instance of given extension
     */
    public static MimeType fromExtension(String ext) {
        for (MimeType mt : values()) {
            if (mt.ext.equals(ext)) {
                return mt;
            }
        }
        return DEFAULT;
    }
}
