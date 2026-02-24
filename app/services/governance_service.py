from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditVerdict,
    CreativeAsset,
    JourneyEventType,
    MultimodalAudit,
    User,
    WorkflowStatus,
)
from app.schemas.governance import (
    AuditResponse,
    GovernanceDecisionResponse,
    ReviewARequest,
    ReviewBRequest,
)
from app.services.gen_ai_service import GenAIService
from app.services.journey_service import log_journey_event
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService
from app.services.workflow import can_transition


@dataclass
class AuditDecision:
    verdict: AuditVerdict
    explanation: str
    confidence: float


def review_by_approver_a(
    *,
    asset_id: str,
    payload: ReviewARequest,
    db: Session,
    current_user: User,
) -> GovernanceDecisionResponse:
    asset = db.scalar(select(CreativeAsset).where(CreativeAsset.id == asset_id))
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    if payload.decision not in {WorkflowStatus.PENDING_B, WorkflowStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approver A can only send to pending_b or rejected",
        )

    if not can_transition(asset.workflow_status, payload.decision):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invalid workflow transition"
        )

    if payload.decision == WorkflowStatus.REJECTED and not payload.rejection_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rejection_reason required when rejected",
        )

    previous_status = asset.workflow_status
    asset.workflow_status = payload.decision
    asset.reviewer_a_id = current_user.id
    asset.rejection_reason = payload.rejection_reason

    event_type, note = _event_for_review(payload)

    log_journey_event(
        db,
        asset_id=asset.id,
        actor_id=current_user.id,
        event_type=event_type,
        from_status=previous_status,
        to_status=payload.decision,
        note=note,
        payload={"rejection_reason": payload.rejection_reason},
    )

    db.commit()

    return GovernanceDecisionResponse(
        asset_id=asset.id,
        workflow_status=asset.workflow_status,
        rejection_reason=asset.rejection_reason,
    )


def audit_with_image(
    *,
    asset_id: str,
    file: UploadFile,
    db: Session,
    current_user: User,
    ai_service: GenAIService,
    rag_service: RagService,
    observability: ObservabilityService,
) -> GovernanceDecisionResponse:
    asset = db.scalar(select(CreativeAsset).where(CreativeAsset.id == asset_id))
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    _assert_status(
        asset.workflow_status == WorkflowStatus.PENDING_B,
        "Asset must be pending_b before multimodal audit",
    )

    rag_query = (
        "Reglas visuales y de identidad de marca para auditar imágenes: "
        "logo, paleta de colores, tipografía, estilo fotográfico, composición, "
        "uso de iconografía, prohibiciones visuales y consistencia de marca."
    )

    rag_context = rag_service.retrieve_relevant_chunks(
        db=db,
        scope_id=asset.manual_id,
        query_text=rag_query,
        top_k=8,
    )

    manual_context = "\n\n".join(rag_context)

    file_bytes = file.file.read()
    image_label = file.filename or f"inline-{uuid4()}.jpg"

    with observability.trace(
        name="multimodal_audit",
        input_data={"asset_id": asset.id, "file_name": file.filename},
        metadata={"user_id": current_user.id},
    ) as span:
        prompt = (
            "Audita la imagen contra el manual de marca. Sigue estas instrucciones al pie de la letra:\n"
            "1) Analiza logo, paleta, tipografía, estilo fotográfico, composición, iconografía y prohibiciones.\n"
            "2) Si algo falla, explica en español cómo corregir la imagen (qué cambiar, remover o ajustar).\n"
            "3) Devuelve SOLO JSON válido según el esquema indicado.\n\n"
            f"Reglas relevantes del manual:\n{manual_context}"
        )
        response_schema = {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["check", "fail"],
                    "description": "check si cumple, fail si incumple",
                },
                "explanation": {
                    "type": "string",
                    "description": "Resumen breve de hallazgos y pasos para corregir la imagen si aplica",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Confianza entre 0 y 1",
                },
            },
            "required": ["verdict", "explanation", "confidence"],
            "additionalProperties": False,
        }
        with observability.generation(
            name="llm.multimodal_audit",
            input_data={
                "prompt": prompt,
                "rag_query": rag_query,
                "rag_context": rag_context,
                "image": {
                    "file_name": file.filename,
                    "label": image_label,
                    "content_type": file.content_type,
                    "size_bytes": len(file_bytes) if file_bytes else 0,
                },
                "asset_id": asset.id,
            },
            metadata={"user_id": current_user.id, "asset_id": asset.id},
            model=ai_service.settings.google_vision_model,
        ) as gen:
            raw_result = ai_service.generate_multimodal_text(
                prompt=prompt,
                image_bytes=file_bytes,
                mime_type=file.content_type or "image/jpeg",
                response_mime_type="application/json",
                response_json_schema=response_schema,
            )
            observability.annotate(gen, {"raw_result": raw_result})
        try:
            result = _parse_audit_decision(raw_result)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Model returned an invalid audit payload",
            ) from exc

        if gen is not None:
            observability.annotate(
                gen,
                {
                    "parsed": {
                        "verdict": result.verdict.value,
                        "confidence": result.confidence,
                        "explanation": result.explanation,
                    }
                },
            )

        previous_status = asset.workflow_status
        next_status = asset.workflow_status

        audit = MultimodalAudit(
            asset_id=asset.id,
            approver_id=current_user.id,
            image_path=image_label,
            verdict=result.verdict,
            explanation=result.explanation,
            confidence=result.confidence,
        )
        db.add(audit)
        db.flush()

        event_type, note = _event_for_audit(result.verdict)
        log_journey_event(
            db,
            asset_id=asset.id,
            actor_id=current_user.id,
            event_type=event_type,
            from_status=previous_status,
            to_status=next_status,
            note=note,
            payload={
                "verdict": result.verdict.value,
                "confidence": result.confidence,
                "explanation": result.explanation,
                "audit_id": audit.id,
            },
        )

        db.commit()
        db.refresh(audit)
        observability.annotate(
            span,
            {
                "asset_id": asset.id,
                "audit_id": audit.id,
                "verdict": result.verdict.value,
                "from_status": previous_status.value,
                "to_status": next_status.value,
                "confidence": result.confidence,
                "explanation": result.explanation,
            },
        )

    return GovernanceDecisionResponse(
        asset_id=asset.id,
        workflow_status=asset.workflow_status,
        rejection_reason=asset.rejection_reason,
        audit=AuditResponse(
            id=audit.id,
            asset_id=audit.asset_id,
            approver_id=audit.approver_id,
            image_path=audit.image_path,
            verdict=audit.verdict,
            explanation=audit.explanation,
            confidence=audit.confidence,
            created_at=audit.created_at,
        ),
    )


def _event_for_review(payload: ReviewARequest) -> tuple[JourneyEventType, str]:
    if payload.decision == WorkflowStatus.PENDING_B:
        return (
            JourneyEventType.REVIEW_A_APPROVED,
            "Approver A aprobó y envió a Approver B",
        )
    return (
        JourneyEventType.REVIEW_A_REJECTED,
        f"Approver A rechazó: {payload.rejection_reason}",
    )


def review_by_approver_b(
    *,
    asset_id: str,
    payload: ReviewBRequest,
    db: Session,
    current_user: User,
) -> GovernanceDecisionResponse:
    asset = db.scalar(select(CreativeAsset).where(CreativeAsset.id == asset_id))
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )

    if payload.decision not in {WorkflowStatus.APPROVED, WorkflowStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approver B can only approve or reject",
        )

    if not can_transition(asset.workflow_status, payload.decision):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invalid workflow transition"
        )

    previous_status = asset.workflow_status
    asset.workflow_status = payload.decision
    asset.reviewer_b_id = current_user.id
    asset.rejection_reason = (
        payload.rejection_reason
        if payload.decision == WorkflowStatus.REJECTED
        else None
    )

    event_type = (
        JourneyEventType.AUDIT_CHECK
        if payload.decision == WorkflowStatus.APPROVED
        else JourneyEventType.AUDIT_FAIL
    )
    note = (
        "Approver B aprobó el recurso"
        if payload.decision == WorkflowStatus.APPROVED
        else f"Approver B rechazó: {payload.rejection_reason}"
    )

    log_journey_event(
        db,
        asset_id=asset.id,
        actor_id=current_user.id,
        event_type=event_type,
        from_status=previous_status,
        to_status=payload.decision,
        note=note,
        payload={
            "decision": payload.decision.value,
            "rejection_reason": payload.rejection_reason,
        },
    )

    db.commit()

    return GovernanceDecisionResponse(
        asset_id=asset.id,
        workflow_status=asset.workflow_status,
        rejection_reason=asset.rejection_reason,
    )


def _event_for_audit(verdict: AuditVerdict) -> tuple[JourneyEventType, str]:
    if verdict == AuditVerdict.CHECK:
        return JourneyEventType.AUDIT_CHECK, "Auditoría multimodal aprobada"
    return JourneyEventType.AUDIT_FAIL, "Auditoría multimodal fallida"


def _parse_audit_decision(text_payload: str) -> AuditDecision:
    parsed = _extract_json_object(text_payload)
    verdict = (
        AuditVerdict.CHECK if parsed.get("verdict") == "check" else AuditVerdict.FAIL
    )

    confidence = float(parsed.get("confidence", 0.5))
    confidence = max(0.0, min(confidence, 1.0))
    explanation = parsed.get("explanation", "No explanation returned")
    return AuditDecision(
        verdict=verdict, confidence=confidence, explanation=explanation
    )


def _extract_json_object(text_payload: str) -> dict:
    cleaned = (text_payload or "").strip()
    if not cleaned:
        raise ValueError("Empty model response")

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _assert_status(condition: bool, detail: str) -> None:
    if not condition:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
