from app.db.models import WorkflowStatus

_ALLOWED_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.PENDING_A: {WorkflowStatus.PENDING_B, WorkflowStatus.REJECTED},
    WorkflowStatus.PENDING_B: {WorkflowStatus.APPROVED, WorkflowStatus.REJECTED},
    WorkflowStatus.APPROVED: set(),
    WorkflowStatus.REJECTED: set(),
}


def can_transition(current: WorkflowStatus, target: WorkflowStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]
