from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BrandManual, User
from app.schemas.brand_manuals import (
    BrandManualCreateRequest,
    BrandManualListResponse,
    BrandManualResponse,
)
from app.services.gen_ai_service import GenAIService
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService


def _to_response(manual: BrandManual) -> BrandManualResponse:
    return BrandManualResponse(
        id=manual.id,
        product_name=manual.product_name,
        tone=manual.tone,
        audience=manual.audience,
        manual_markdown=manual.manual_markdown,
        created_by_id=manual.created_by_id,
        created_at=manual.created_at,
    )


def create_brand_manual(
    *,
    payload: BrandManualCreateRequest,
    db: Session,
    current_user: User,
    ai_service: GenAIService,
    rag_service: RagService,
    observability: ObservabilityService,
) -> BrandManualResponse:
    system_prompt = "Eres estratega de marca senior. Produces guías concretas, medibles y sin contradicciones."

    user_prompt = (
        "Genera un manual de marca estructurado y accionable para el equipo creativo. "
        "Responde en JSON válido según el esquema. Cada sección debe ser concreta y sin contradicciones."
        "\n\n"
        "Secciones obligatorias (usa estos títulos exactos):\n"
        "1) Esencia de marca\n"
        "2) Voz y tono\n"
        "3) Do/Don't de lenguaje\n"
        "4) Reglas visuales\n"
        "5) Reglas de compliance\n\n"
        f"Producto: {payload.product_name}\n"
        f"Tono: {payload.tone}\n"
        f"Público: {payload.audience}\n"
        f"Contexto extra: {payload.extra_context or 'Ninguno'}"
    )

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "brand_manual",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["title", "content"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["sections"],
                "additionalProperties": False,
            },
        },
    }

    with observability.trace(
        name="brand_manual_generation",
        input_data=payload.model_dump(),
        metadata={"user_id": current_user.id},
    ) as span:
        with observability.generation(
            name="llm.generate_brand_manual",
            input_data={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": 0.2,
                "response_format": response_format,
            },
            metadata={"user_id": current_user.id},
            model=ai_service.settings.groq_model,
            model_parameters={"temperature": 0.2},
        ) as gen:
            manual_payload = ai_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                response_format=response_format,
            )
            observability.annotate(gen, {"raw_manual_payload": manual_payload})

        manual_data = json.loads(manual_payload)
        sections = manual_data.get("sections") or []
        manual_text = "\n\n".join(
            f"## {section['title'].strip()}\n{section['content'].strip()}"
            for section in sections
            if section.get("title") and section.get("content")
        ).strip()

        manual = BrandManual(
            product_name=payload.product_name,
            tone=payload.tone,
            audience=payload.audience,
            raw_input=payload.model_dump_json(),
            manual_markdown=manual_text,
            created_by_id=current_user.id,
        )

        db.add(manual)
        db.flush()

        rag_service.index_content(
            db=db,
            scope_id=manual.id,
            content_text=manual_text,
            separator="##",
        )

        db.commit()
        db.refresh(manual)

        observability.annotate(
            span,
            {
                "manual_id": manual.id,
                "manual_markdown": manual_text,
            },
        )

    return _to_response(manual)


def list_brand_manuals(*, db: Session) -> BrandManualListResponse:
    manuals = db.scalars(
        select(BrandManual).order_by(BrandManual.created_at.desc())
    ).all()

    return BrandManualListResponse(items=[_to_response(item) for item in manuals])
