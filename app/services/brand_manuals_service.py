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
    system_prompt = (
        "Actúa como consultor senior en branding, identidad corporativa y diseño estratégico "
        "con experiencia en desarrollo de manuales de marca para empresas de distintos sectores.\n\n"
        "Tu objetivo es generar un manual de marca claro, coherente, estructurado y profesional, listo "
        "para ser entregado a equipos de diseño, marketing y comunicación.\n\n"
        "El manual debe:\n"
        "- Tener estructura jerárquica clara (títulos y subtítulos).\n"
        "- Usar lenguaje técnico pero comprensible.\n"
        "- Mantener coherencia estratégica entre identidad, posicionamiento y elementos visuales.\n"
        "- Evitar redundancias.\n"
        "- Justificar brevemente las decisiones estratégicas.\n"
        "- No incluir explicaciones meta ni comentarios sobre el proceso.\n"
        "- No incluir ejemplos ficticios irrelevantes.\n"
        "- Mantener consistencia conceptual en todo el documento.\n\n"
        "Debe incluir como mínimo estas secciones:\n"
        "1. Fundamentos estratégicos\n"
        "- Propósito\n"
        "- Misión\n"
        "- Visión\n"
        "- Valores\n"
        "- Propuesta de valor\n"
        "- Público objetivo\n"
        "2. Personalidad y tono\n"
        "- Arquetipo de marca\n"
        "- Rasgos de personalidad\n"
        "- Voz y tono\n"
        "- Lineamientos de comunicación\n"
        "3. Identidad visual\n"
        "- Concepto del logotipo\n"
        "- Versiones del logotipo\n"
        "- Área de protección\n"
        "- Tamaño mínimo\n"
        "- Usos correctos\n"
        "- Usos incorrectos\n"
        "- Paleta cromática (primaria y secundaria con códigos HEX y RGB)\n"
        "- Tipografías (primarias y secundarias con usos definidos)\n"
        "- Sistema gráfico (iconografía, patrones, recursos visuales si aplica)\n"
        "4. Aplicaciones básicas\n"
        "- Papelería corporativa\n"
        "- Aplicación digital\n"
        "- Redes sociales\n"
        "- Material promocional"
    )

    user_prompt = (
        "Genera un manual de marca estructurado, coherente y accionable para el equipo creativo teniendo en cuenta las siguientes especificaciones:"
        "\n\n"
        f'Producto: "{payload.product_name}"\n'
        f'Tono: "{payload.tone}"\n'
        f'Público: "{payload.audience}"\n'
        f'Contexto extra: "{payload.extra_context or "Ninguno"}"'
        "\n\n"
        "Responde en JSON válido según el esquema."
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
