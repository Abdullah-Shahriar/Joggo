from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import Date, cast, desc, func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.complaint import Complaint, ComplaintMessage, ComplaintStatus
from app.models.document import Document, DocumentStatus
from app.models.entity import DocumentEntity
from app.models.llm_request import LLMRequest, LLMRequestStatus
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.models.user import User, UserStatus
from app.schemas.admin import (
    ActivityDayItem,
    AdminAnalyticsResponse,
    AdminOverviewResponse,
    DailyDocumentStatusCounts,
    DashboardResponse,
    EntityTypeCount,
)
from app.schemas.document import DocumentListItem

HEATMAP_DAYS = 91  # 13 full weeks


def _build_activity_heatmap(
    db: Session,
    *,
    actor_id: uuid.UUID | None = None,
    days: int = HEATMAP_DAYS,
) -> list[ActivityDayItem]:
    """Build daily activity breakdown over the last N days using aggregate SQL counts only (P7)."""
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    buckets: dict[str, dict[str, int]] = {}
    for offset in range(days):
        d_str = (start_day + timedelta(days=offset)).date().isoformat()
        buckets[d_str] = {
            "documents_uploaded": 0,
            "reviews_and_marks": 0,
            "generations_completed": 0,
            "comments_and_help": 0,
        }

    # 1. Documents uploaded
    doc_day = cast(func.timezone("UTC", Document.created_at), Date).label("day")
    doc_stmt = select(doc_day, func.count(Document.id)).where(Document.created_at >= start_day)
    if actor_id is not None:
        doc_stmt = doc_stmt.where(Document.owner_id == actor_id)
    for day_val, cnt in db.execute(doc_stmt.group_by(doc_day)).all():
        key = day_val.isoformat()
        if key in buckets:
            buckets[key]["documents_uploaded"] += int(cnt)

    # 2. Reviews, manual marks, approvals, and completions from audit_logs
    audit_day = cast(func.timezone("UTC", AuditLog.ts), Date).label("day")
    tracked_actions = ("DOC_MANUAL_MARK", "DOC_APPROVE", "DOC_COMPLETE", "DOC_EXPORT")
    audit_stmt = select(audit_day, AuditLog.action, func.count(AuditLog.id)).where(
        AuditLog.ts >= start_day,
        AuditLog.action.in_(tracked_actions),
    )
    if actor_id is not None:
        audit_stmt = audit_stmt.where(AuditLog.actor_id == actor_id)
    for day_val, act, cnt in db.execute(audit_stmt.group_by(audit_day, AuditLog.action)).all():
        key = day_val.isoformat()
        if key not in buckets:
            continue
        if act in ("DOC_MANUAL_MARK", "DOC_APPROVE"):
            buckets[key]["reviews_and_marks"] += int(cnt)
        elif act in ("DOC_COMPLETE", "DOC_EXPORT"):
            buckets[key]["generations_completed"] += int(cnt)

    # 3. Complaints filed + comment replies
    comp_day = cast(func.timezone("UTC", Complaint.created_at), Date).label("day")
    comp_stmt = select(comp_day, func.count(Complaint.id)).where(Complaint.created_at >= start_day)
    if actor_id is not None:
        comp_stmt = comp_stmt.where(Complaint.user_id == actor_id)
    for day_val, cnt in db.execute(comp_stmt.group_by(comp_day)).all():
        key = day_val.isoformat()
        if key in buckets:
            buckets[key]["comments_and_help"] += int(cnt)

    msg_day = cast(func.timezone("UTC", ComplaintMessage.created_at), Date).label("day")
    msg_stmt = select(msg_day, func.count(ComplaintMessage.id)).where(ComplaintMessage.created_at >= start_day)
    if actor_id is not None:
        msg_stmt = msg_stmt.where(ComplaintMessage.author_id == actor_id)
    for day_val, cnt in db.execute(msg_stmt.group_by(msg_day)).all():
        key = day_val.isoformat()
        if key in buckets:
            buckets[key]["comments_and_help"] += int(cnt)

    return [
        ActivityDayItem(
            date=d_str,
            total=(
                vals["documents_uploaded"]
                + vals["reviews_and_marks"]
                + vals["generations_completed"]
                + vals["comments_and_help"]
            ),
            documents_uploaded=vals["documents_uploaded"],
            reviews_and_marks=vals["reviews_and_marks"],
            generations_completed=vals["generations_completed"],
            comments_and_help=vals["comments_and_help"],
        )
        for d_str, vals in buckets.items()
    ]


def get_doctor_dashboard(db: Session, owner_id: uuid.UUID) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    status_rows = db.execute(
        select(Document.status, func.count(Document.id))
        .where(Document.owner_id == owner_id)
        .group_by(Document.status)
    ).all()
    counts_by_status = {status.value: int(cnt) for status, cnt in status_rows}

    processed_last_7 = int(
        db.execute(
            select(func.count(Document.id)).where(
                Document.owner_id == owner_id,
                Document.created_at >= seven_days_ago,
                Document.status.in_(
                    [
                        DocumentStatus.REVIEW_REQUIRED,
                        DocumentStatus.APPROVED,
                        DocumentStatus.COMPLETED,
                    ]
                ),
            )
        ).scalar_one()
    )

    recent_docs = (
        db.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(desc(Document.created_at))
            .limit(5)
        )
        .scalars()
        .all()
    )

    top_entities = db.execute(
        select(DocumentEntity.entity_type, func.sum(DocumentEntity.occurrences).label("total"))
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(Document.owner_id == owner_id)
        .group_by(DocumentEntity.entity_type)
        .order_by(desc("total"), DocumentEntity.entity_type.asc())
        .limit(5)
    ).all()

    # Average pipeline seconds from EXTRACT.started_at to SAFETY_CHECK.finished_at
    extract_steps = (
        select(PipelineStep.document_id, PipelineStep.started_at)
        .join(Document, Document.id == PipelineStep.document_id)
        .where(
            Document.owner_id == owner_id,
            PipelineStep.step == PipelineStepName.EXTRACT,
            PipelineStep.status == PipelineStepStatus.succeeded,
            PipelineStep.started_at.is_not(None),
        )
        .subquery()
    )
    safety_steps = (
        select(PipelineStep.document_id, PipelineStep.finished_at)
        .join(Document, Document.id == PipelineStep.document_id)
        .where(
            Document.owner_id == owner_id,
            PipelineStep.step == PipelineStepName.SAFETY_CHECK,
            PipelineStep.status == PipelineStepStatus.succeeded,
            PipelineStep.finished_at.is_not(None),
        )
        .subquery()
    )
    avg_secs_raw = db.execute(
        select(
            func.avg(
                func.extract("epoch", safety_steps.c.finished_at - extract_steps.c.started_at)
            )
        ).select_from(
            extract_steps.join(safety_steps, extract_steps.c.document_id == safety_steps.c.document_id)
        )
    ).scalar_one_or_none()
    avg_secs = round(float(avg_secs_raw), 2) if avg_secs_raw is not None else None

    return DashboardResponse(
        counts_by_status=counts_by_status,
        processed_last_7_days=processed_last_7,
        waiting_for_review=counts_by_status.get(DocumentStatus.REVIEW_REQUIRED.value, 0),
        blocked_count=counts_by_status.get(DocumentStatus.BLOCKED.value, 0),
        recent_documents=[
            DocumentListItem(
                id=d.id,
                original_filename=d.original_filename,
                size_bytes=d.size_bytes,
                page_count=d.page_count,
                task_type=d.task_type.value,
                status=d.status.value,
                entity_count=sum((d.entity_summary or {}).values()),
                vault_expired=d.vault_expired,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in recent_docs
        ],
        top_entity_types=[
            EntityTypeCount(entity_type=etype, count=int(total)) for etype, total in top_entities
        ],
        avg_pipeline_seconds=avg_secs,
        activity_heatmap=_build_activity_heatmap(db, actor_id=owner_id),
    )


def get_admin_overview(db: Session) -> AdminOverviewResponse:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_complaints = int(
        db.execute(
            select(func.count(Complaint.id)).where(Complaint.status == ComplaintStatus.open)
        ).scalar_one()
    )
    in_progress_complaints = int(
        db.execute(
            select(func.count(Complaint.id)).where(Complaint.status == ComplaintStatus.in_progress)
        ).scalar_one()
    )
    restricted_users = int(
        db.execute(
            select(func.count(User.id)).where(User.status == UserStatus.restricted)
        ).scalar_one()
    )
    docs_today = int(
        db.execute(
            select(func.count(Document.id)).where(Document.created_at >= today_start)
        ).scalar_one()
    )

    return AdminOverviewResponse(
        open_complaints=open_complaints,
        in_progress_complaints=in_progress_complaints,
        restricted_users=restricted_users,
        documents_processed_today=docs_today,
    )


def get_admin_analytics(db: Session) -> AdminAnalyticsResponse:
    """Aggregate-only admin analytics via SQL GROUP BY (rules.md P7, architecture.md §21)."""
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)

    role_rows = db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()
    users_by_role = {role.value: int(cnt) for role, cnt in role_rows}

    status_rows = db.execute(select(User.status, func.count(User.id)).group_by(User.status)).all()
    users_by_status = {st.value: int(cnt) for st, cnt in status_rows}

    # Documents by status per day for the last 14 days
    day_col = cast(func.timezone("UTC", Document.created_at), Date).label("day")
    daily_rows = db.execute(
        select(day_col, Document.status, func.count(Document.id))
        .where(Document.created_at >= start_day)
        .group_by(day_col, Document.status)
        .order_by(day_col.asc())
    ).all()

    daily_map: dict[str, dict[str, int]] = {}
    for offset in range(14):
        d_str = (start_day + timedelta(days=offset)).date().isoformat()
        daily_map[d_str] = {}
    for day_val, st, cnt in daily_rows:
        d_str = day_val.isoformat()
        if d_str in daily_map:
            daily_map[d_str][st.value] = int(cnt)

    documents_per_day = [
        DailyDocumentStatusCounts(
            date=d_str,
            total=sum(by_st.values()),
            by_status=by_st,
        )
        for d_str, by_st in daily_map.items()
    ]

    # LLM provider usage & latency
    provider_rows = db.execute(
        select(LLMRequest.provider, func.count(LLMRequest.id))
        .where(LLMRequest.provider.is_not(None), LLMRequest.status == LLMRequestStatus.succeeded)
        .group_by(LLMRequest.provider)
    ).all()
    llm_provider_usage = {str(prov): int(cnt) for prov, cnt in provider_rows}

    llm_fallback_count = int(
        db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.action == "DOC_LLM_FALLBACK")
        ).scalar_one()
    )

    avg_lat_raw = db.execute(
        select(func.avg(LLMRequest.latency_ms)).where(
            LLMRequest.status == LLMRequestStatus.succeeded,
            LLMRequest.latency_ms.is_not(None),
        )
    ).scalar_one_or_none()
    avg_llm_latency_ms = round(float(avg_lat_raw), 2) if avg_lat_raw is not None else None

    # Complaints by status
    comp_rows = db.execute(
        select(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status)
    ).all()
    complaints_by_status = {st.value: int(cnt) for st, cnt in comp_rows}

    # Safety block rate (blocked audits / total safety-checked documents)
    total_scanned = int(
        db.execute(
            select(func.count(Document.id)).where(Document.safety_report.is_not(None))
        ).scalar_one()
    )
    total_blocked = int(
        db.execute(
            select(func.count(Document.id)).where(Document.status == DocumentStatus.BLOCKED)
        ).scalar_one()
    )
    safety_block_rate = round(total_blocked / total_scanned, 4) if total_scanned > 0 else 0.0

    # Entity type totals (counts only, no values)
    ent_rows = db.execute(
        select(DocumentEntity.entity_type, func.sum(DocumentEntity.occurrences).label("total"))
        .group_by(DocumentEntity.entity_type)
        .order_by(desc("total"), DocumentEntity.entity_type.asc())
    ).all()
    entity_type_totals = [EntityTypeCount(entity_type=et, count=int(tot)) for et, tot in ent_rows]

    return AdminAnalyticsResponse(
        users_by_role=users_by_role,
        users_by_status=users_by_status,
        documents_per_day=documents_per_day,
        llm_provider_usage=llm_provider_usage,
        llm_fallback_count=llm_fallback_count,
        avg_llm_latency_ms=avg_llm_latency_ms,
        complaints_by_status=complaints_by_status,
        safety_block_rate=safety_block_rate,
        entity_type_totals=entity_type_totals,
        activity_heatmap=_build_activity_heatmap(db, actor_id=None),
    )
