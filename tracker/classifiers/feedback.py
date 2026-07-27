# -*- coding: utf-8 -*-
"""사용자 승인/수정/거절 피드백 저장 + 이후 분류에 재사용(재훈련 아님, 규칙 참고).

원칙: 사용자 피드백만으로 외부 추정치를 공식으로 승격하지 않는다(공식여부는 원출처·근거 우선).
피드백은 '자동확정을 더 보수적으로' 만드는 방향으로만 사용(같은 도메인 오분류 이력 → review 강제).
"""
from __future__ import annotations
from tracker.database import db


def record(conn, *, candidate_id=None, source_domain="", original_classification="",
           final_classification="", original_metric_scope="", final_metric_scope="",
           original_qualifier="", final_qualifier="", approval_action="",
           correction_reason="", evidence_pattern="") -> None:
    conn.execute(
        "INSERT INTO classification_feedback (candidate_id, source_domain, "
        "original_classification, final_classification, original_metric_scope, "
        "final_metric_scope, original_qualifier, final_qualifier, approval_action, "
        "correction_reason, evidence_pattern, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (candidate_id, source_domain, original_classification, final_classification,
         original_metric_scope, final_metric_scope, original_qualifier, final_qualifier,
         approval_action, correction_reason, evidence_pattern, db.now_kst()))
    conn.commit()


def domain_should_review(conn, domain: str, min_events: int = 1) -> bool:
    """이 도메인에서 과거 '거절' 또는 '분류/스코프 정정' 이력이 있으면 신규 자동확정을 막고 review 로."""
    if not domain:
        return False
    row = db.fetchone(
        conn,
        "SELECT COUNT(*) FROM classification_feedback WHERE source_domain=? AND "
        "(approval_action='reject' OR original_metric_scope<>final_metric_scope "
        "OR original_classification<>final_classification)",
        (domain,))
    return bool(row and (row[0] or 0) >= min_events)


def domain_accuracy(conn, domain: str) -> dict:
    """도메인별 승인/거절 이력 요약(참고 표시용)."""
    rows = db.fetchall(conn, "SELECT approval_action, COUNT(*) FROM classification_feedback "
                             "WHERE source_domain=? GROUP BY approval_action", (domain,))
    return {r[0]: r[1] for r in rows}
