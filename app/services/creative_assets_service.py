from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AssetJourneyEvent,
    AssetType,
    BrandManual,
    CreativeAsset,
    JourneyEventType,
    Role,
    User,
    WorkflowStatus,
)
from app.schemas.creative_assets import (
    CreativeAssetHistoryItemResponse,
    CreativeAssetHistoryListResponse,
    CreativeAssetJourneyResponse,
    CreativeAssetListResponse,
    CreativeAssetResponse,
    CreativeGenerateRequest,
    CreativeGenerateResponse,
    JourneyEventResponse,
)
from app.services.gen_ai_service import GenAIService
from app.services.journey_service import log_journey_event
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService


def _to_asset_response(asset: CreativeAsset) -> CreativeAssetResponse:
    return CreativeAssetResponse(
        id=asset.id,
        manual_id=asset.manual_id,
        created_by_id=asset.created_by_id,
        asset_type=asset.asset_type,
        brief=asset.brief,
        generated_text=asset.generated_text,
        workflow_status=asset.workflow_status,
        rejection_reason=asset.rejection_reason,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _to_history_response(asset: CreativeAsset) -> CreativeAssetHistoryItemResponse:
    latest_audit = (
        max(asset.audits, key=lambda audit: audit.created_at) if asset.audits else None
    )

    base = _to_asset_response(asset).model_dump()
    return CreativeAssetHistoryItemResponse(
        **base,
        manual_product_name=asset.manual.product_name,
        manual_markdown=asset.manual.manual_markdown,
        latest_audit_verdict=latest_audit.verdict if latest_audit else None,
        latest_audit_explanation=latest_audit.explanation if latest_audit else None,
        latest_audit_confidence=latest_audit.confidence if latest_audit else None,
        latest_audit_at=latest_audit.created_at if latest_audit else None,
    )


def _to_journey_event(event: AssetJourneyEvent) -> JourneyEventResponse:
    actor = event.actor
    return JourneyEventResponse(
        id=event.id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        note=event.note,
        actor_id=event.actor_id,
        actor_name=actor.full_name if actor else None,
        actor_role=actor.role if actor else None,
        payload=event.payload,
        created_at=event.created_at,
    )


def _get_manual_or_404(*, db: Session, manual_id: str) -> BrandManual:
    manual = db.scalar(select(BrandManual).where(BrandManual.id == manual_id))
    if not manual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found"
        )
    return manual


def _build_creative_prompts(
    *, asset_type: AssetType, brief: str, context_chunks: list[str]
) -> tuple[str, str]:
    task_map = {
        AssetType.PRODUCT_DESCRIPTION: "Escribe descripción de producto lista para ecommerce.",
        AssetType.VIDEO_SCRIPT: "Escribe guión corto de video vertical (30-45s).",
        AssetType.IMAGE_PROMPT: "Escribe prompt de imagen hiper-claro para generador visual.",
    }

    context_text = "\n\n".join(context_chunks[:4])

    system_prompt = (
        "Eres copywriter senior orientado a performance y consistencia de marca."
    )

    user_prompt = (
        f"Tarea: {task_map[asset_type]}\n"
        f"Brief: {brief}\n\n"
        "Contexto obligatorio del manual de marca (debe respetarse):\n"
        f"{context_text}\n\n"
        "Si hay conflicto, prioriza reglas del manual."
    )

    return system_prompt, user_prompt


def generate_asset(
    *,
    payload: CreativeGenerateRequest,
    db: Session,
    current_user: User,
    ai_service: GenAIService,
    rag_service: RagService,
    observability: ObservabilityService,
) -> CreativeGenerateResponse:
    manual = _get_manual_or_404(db=db, manual_id=payload.manual_id)

    with observability.trace(
        name="creative_generation",
        input_data=payload.model_dump(),
        metadata={"user_id": current_user.id, "manual_id": payload.manual_id},
    ) as span:
        rag_query = (
            f"Brief: {payload.brief}\n"
            f"Tipo de asset: {payload.asset_type.value}\n"
            f"Producto: {manual.product_name}\n"
            f"Tono: {manual.tone}\n"
            f"Público: {manual.audience}"
        )

        rag_context = rag_service.retrieve_relevant_chunks(
            db=db,
            scope_id=payload.manual_id,
            query_text=rag_query,
            top_k=10,
        )

        system_prompt, user_prompt = _build_creative_prompts(
            asset_type=payload.asset_type,
            brief=payload.brief,
            context_chunks=rag_context,
        )

        with observability.generation(
            name="llm.generate_creative_asset",
            input_data={
                "rag_query": rag_query,
                "rag_context": rag_context,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": 0.45,
                "asset_type": payload.asset_type.value,
            },
            metadata={"user_id": current_user.id, "manual_id": payload.manual_id},
            model=ai_service.settings.groq_model,
            model_parameters={"temperature": 0.45},
        ) as gen:
            generated_text = ai_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.45,
            )
            observability.annotate(gen, {"generated_text": generated_text})

        asset = CreativeAsset(
            manual_id=payload.manual_id,
            created_by_id=current_user.id,
            asset_type=payload.asset_type,
            brief=payload.brief,
            generated_text=generated_text,
            workflow_status=WorkflowStatus.PENDING_A,
        )

        db.add(asset)
        db.flush()

        log_journey_event(
            db,
            asset_id=asset.id,
            actor_id=current_user.id,
            event_type=JourneyEventType.ASSET_CREATED,
            from_status=None,
            to_status=WorkflowStatus.PENDING_A,
            note="Asset creado por Creator y enviado a Approver A",
            payload={
                "manual_id": payload.manual_id,
                "asset_type": payload.asset_type.value,
            },
        )

        db.commit()
        db.refresh(asset)

        observability.annotate(
            span,
            {
                "asset_id": asset.id,
                "generated_text": generated_text,
                "rag_query": rag_query,
                "rag_context": rag_context,
            },
        )

    return CreativeGenerateResponse(
        asset=_to_asset_response(asset), rag_context=rag_context
    )


def list_assets(
    *,
    status_filter: WorkflowStatus | None,
    db: Session,
    current_user: User,
) -> CreativeAssetListResponse:
    query = select(CreativeAsset).order_by(CreativeAsset.created_at.desc())

    role_filter = {
        Role.CREATOR: CreativeAsset.created_by_id == current_user.id,
        Role.APPROVER_A: CreativeAsset.workflow_status == WorkflowStatus.PENDING_A,
        Role.APPROVER_B: CreativeAsset.workflow_status == WorkflowStatus.PENDING_B,
    }.get(current_user.role)
    if role_filter is not None:
        query = query.where(role_filter)

    if status_filter:
        query = query.where(CreativeAsset.workflow_status == status_filter)

    assets = db.scalars(query).all()

    return CreativeAssetListResponse(
        items=[_to_asset_response(asset) for asset in assets]
    )


def list_assets_history(
    *,
    asset_type_filter: AssetType | None,
    db: Session,
) -> CreativeAssetHistoryListResponse:
    query = (
        select(CreativeAsset)
        .options(selectinload(CreativeAsset.manual), selectinload(CreativeAsset.audits))
        .order_by(CreativeAsset.created_at.desc())
    )

    if asset_type_filter:
        query = query.where(CreativeAsset.asset_type == asset_type_filter)

    assets = db.scalars(query).all()

    return CreativeAssetHistoryListResponse(
        items=[_to_history_response(asset) for asset in assets]
    )


def get_asset_journey(
    *,
    asset_id: str,
    db: Session,
) -> CreativeAssetJourneyResponse:
    asset = db.scalar(
        select(CreativeAsset)
        .where(CreativeAsset.id == asset_id)
        .options(
            selectinload(CreativeAsset.manual),
            selectinload(CreativeAsset.audits),
            selectinload(CreativeAsset.journey_events).selectinload(
                AssetJourneyEvent.actor
            ),
        )
    )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    if not asset.journey_events:
        legacy_event = JourneyEventResponse(
            id=f"legacy-{asset.id}",
            event_type=JourneyEventType.ASSET_CREATED,
            from_status=None,
            to_status=asset.workflow_status,
            note="Este registro no tenía eventos históricos.",
            actor_id=asset.created_by_id,
            actor_name=None,
            actor_role=None,
            payload={"legacy": True},
            created_at=asset.created_at,
        )

        return CreativeAssetJourneyResponse(
            asset=_to_history_response(asset),
            events=[legacy_event],
        )

    return CreativeAssetJourneyResponse(
        asset=_to_history_response(asset),
        events=[_to_journey_event(event) for event in asset.journey_events],
    )
