from google.genai import types
from .config import Config

BASE_PROMPT = (
    "You are a document classification assistant.\n"
    "Return ONLY the document_type from the list: \n"
    "[ELECTRICITY_BILL, WATER_BILL, BANK_STATEMENT, ID_CARD, DRIVERS_LICENSE]"
)

class GeminiClassifier:

    def __init__(self, genai_client, model: str= Config.TUNED_MODEL):
        self.client = genai_client
        self.model = model

    def classify(self, image_bytes: bytes) -> str:
        parts = [
            types.Part.from_text(text=BASE_PROMPT),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ]
        resp = self.client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=16,
            ),
        )
        return resp.text.strip().upper()