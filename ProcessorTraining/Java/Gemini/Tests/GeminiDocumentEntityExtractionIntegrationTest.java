package com.moniepoint.dvs.processor.entities;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ServiceAccountCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.vertexai.VertexAI;
import com.google.cloud.vertexai.generativeai.GenerativeModel;
import com.moniepoint.dvs.component.ConfigurationManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;

import java.io.FileInputStream;
import java.nio.file.Files;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.*;


@SpringBootTest(properties = {"spring.kafka.enabled=false"}, classes = {GeminiDocumentEntityExtractionIntegrationTest.TestConfig.class, GeminiDocumentEntityExtraction.class})
@EnableAutoConfiguration(exclude = {KafkaAutoConfiguration.class, org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration.class})
@TestPropertySource(properties = {"gemini.project.id=1027521807", "gemini.serviceaccount.key=adg-documentai-sa-key.json", "gemini.cloud.region=us-central1", "gemini.model.name=gemini-2.0-flash-lite", "gemini.documents.output.file=gemini_entities.csv", "gemini.input.documents.bucket=adg-delivery-moniepoint-docs-bucket-001", "gemini.input.documents.directory=training-documents/", "gemini.output.documents.json=gemini-entities.json"})
class GeminiDocumentEntityExtractionIntegrationTest {

  @Autowired
  private GeminiDocumentEntityExtraction geminiDocumentEntityExtraction;

  @Test
  void geminiTest() throws Exception {
    String json = assertDoesNotThrow(() ->
      geminiDocumentEntityExtraction.run());


    assertNotNull(json, "JSON return value should not be null");
    String trimmed = json.trim();
    assertTrue(trimmed.startsWith("["), "should start with [");
    assertTrue(trimmed.endsWith("]"), "should end with ]");

    JsonNode root = assertDoesNotThrow(() -> new ObjectMapper().readTree(json));
    assertTrue(root.isArray(), "root must be JSON array");

    assertTrue(
      Files.exists(Paths.get("gemini-entities.json")),
      "expected JSON file to exist"
    );
  }

  @TestConfiguration
  static class TestConfig {
    @Autowired
    private Environment environment;

    @Bean
    public GeminiDocumentEntityExtraction.CsvOutputWriter csvOutputWriter() throws Exception {
      ConfigurationManager configManager = configurationManager();
      String outputFile = configManager.getConfiguration("gemini.documents.output.file");
      return new GeminiDocumentEntityExtraction.CsvOutputWriter(outputFile);
    }


    @Bean
    public ConfigurationManager configurationManager() {
      return new ConfigurationManager() {
        @Override
        public String getConfiguration(String key) {
          return environment.getProperty(key);
        }
      };
    }

    @Bean
    public Storage storage() throws Exception {
      ConfigurationManager configManager = configurationManager();
      String PROJECT_ID = configManager.getConfiguration("gemini.project.id");
      String GCP_KEY_PATH = configManager.getConfiguration("gemini.serviceaccount.key");

      GoogleCredentials creds = ServiceAccountCredentials.fromStream(new FileInputStream(GCP_KEY_PATH))
                                                         .createScoped("https://www.googleapis.com/auth/cloud-platform");

      return StorageOptions.newBuilder()
                           .setProjectId(PROJECT_ID)
                           .setCredentials(creds)
                           .build()
                           .getService();
    }

    @Bean
    public GenerativeModel generativeModel() throws Exception {
      ConfigurationManager configManager = configurationManager();
      String GCP_KEY_PATH = configManager.getConfiguration("gemini.serviceaccount.key");
      String PROJECT_ID = configManager.getConfiguration("gemini.project.id");
      String REGION = configManager.getConfiguration("gemini.cloud.region");
      String MODEL_NAME = configManager.getConfiguration("gemini.model.name");

      GoogleCredentials creds = ServiceAccountCredentials.fromStream(new FileInputStream(GCP_KEY_PATH))
                                                         .createScoped("https://www.googleapis.com/auth/cloud-platform");

      VertexAI vertexAi = new VertexAI.Builder().setProjectId(PROJECT_ID)
                                                .setLocation(REGION)
                                                .setCredentials(creds)
                                                .build();
      return new GenerativeModel(MODEL_NAME,
                                 vertexAi);
    }
  }
}