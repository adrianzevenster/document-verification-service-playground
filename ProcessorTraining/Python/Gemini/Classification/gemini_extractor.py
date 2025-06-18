import json
from google.genai import types
from .config import Config

PROMPT = (
    "You are a document-understanding assistant.\n"
    "Extract the following fields and output ONLY a JSON array of objects:\n"
    "- Supply Address\n- Service Address\n- Customer Name\n- Period\n"
    "- Meter Number\n- Meter #\n- Meter Type\n- Transaction Date\n"
    "- Address\n- Bill Month\n- Customer Account\n- providerAcronym\n\n"
    "Each object must have:\n"
    '  "entity": field name,\n'
    '  "value": extracted text,\n'
    '  "confidence": float between 0.0 and 1.0\n\n'
    "If a field is missing, omit it. DO NOT output any extra text."
)

class GeminiExtractor:
    """Calls Gemini to extract entities from a single page image."""

    def __init__(self, genai_client, model: str = Config.TUNED_MODEL):
        self.client = genai_client
        self.model  = model

    def call(self, image_bytes: bytes) -> list[dict]:
        parts = [
            types.Part.from_text(text=PROMPT),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ]
        resp = self.client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=1024,
            ),
        )
        raw = resp.text.strip()
        # strip ```json\n … ``` fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.splitlines()[1:-1])
        return json.loads(raw)
