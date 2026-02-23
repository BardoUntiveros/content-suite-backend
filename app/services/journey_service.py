from sqlalchemy.orm import Session

from app.db.models import AssetJourneyEvent, JourneyEventType, WorkflowStatus


def log_journey_event(
    db: Session,
    *,
    asset_id: str,
    actor_id: str | None,
    event_type: JourneyEventType,
    to_status: WorkflowStatus,
    note: str,
    from_status: WorkflowStatus | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        AssetJourneyEvent(
            asset_id=asset_id,
            actor_id=actor_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            note=note,
            payload=payload,
        )
    )
