from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import Settings


from groq import Groq
from google import genai
from google.genai import types


class GenAIService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.groq_client = Groq(api_key=settings.groq_api_key)
        self.google_client = genai.Client(api_key=settings.google_api_key)

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        response = self.groq_client.chat.completions.create(
            model=model or self.settings.groq_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
        )
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("Groq returned an empty response")

        return content

    def generate_multimodal_text(
        self,
        *,
        prompt: str,
        image_bytes: bytes | None = None,
        mime_type: str = "image/jpeg",
        model: str | None = None,
        response_mime_type: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> str:
        parts: Sequence[Any] = [prompt]
        if types and hasattr(types, "Part"):
            part_items: list[Any] = [types.Part.from_text(text=prompt)]
            if image_bytes:
                part_items.append(
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                )
            parts = part_items

        response = self.google_client.models.generate_content(
            model=model or self.settings.google_vision_model,
            contents=parts,
            config={
                "response_mime_type": response_mime_type,
                "response_json_schema": response_json_schema,
            },
        )
        text_payload = (getattr(response, "text", "") or "").strip()

        if not text_payload:
            raise RuntimeError("Google model returned an empty response")

        return text_payload
