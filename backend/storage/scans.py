from __future__ import annotations

import json
import uuid
from typing import Any

from backend.models.analysis import AnalysisResponse, ChatMessage
from backend.models.project import ProjectSummary, ScanStatus, StageStatus
from backend.utils.helpers import iso, utcnow

from . import db


class ScanStore:
    def create_scan(self, owner: str, repo: str) -> str:
        scan_id = uuid.uuid4().hex
        now = iso()
        db.execute(
            "INSERT INTO scans (id, owner, repo, status, progress, started_at)"
            " VALUES (?,?,?,?,?,?)",
            (scan_id, owner, repo, "pending", 0.0, now),
        )
        return scan_id

    def get(self, scan_id: str) -> dict[str, Any] | None:
        row = db.query_one("SELECT * FROM scans WHERE id = ?", (scan_id,))
        return dict(row) if row else None

    def latest_for(self, owner: str, repo: str) -> dict[str, Any] | None:
        row = db.query_one(
            "SELECT * FROM scans WHERE owner = ? AND repo = ?"
            " ORDER BY started_at DESC LIMIT 1",
            (owner, repo),
        )
        return dict(row) if row else None

    def update(
        self,
        scan_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        branch: str | None = None,
        error: str | None = None,
        error_details: str | None = None,
        stages: list[StageStatus] | None = None,
        finished: bool = False,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if progress is not None:
            sets.append("progress = ?")
            params.append(round(float(progress), 4))
        if branch is not None:
            sets.append("branch = ?")
            params.append(branch)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if error_details is not None:
            sets.append("error_details = ?")
            params.append(error_details)
        if stages is not None:
            sets.append("stages_json = ?")
            params.append(json.dumps([s.model_dump() for s in stages]))
        if finished:
            sets.append("finished_at = ?")
            params.append(iso())
        if not sets:
            return
        params.append(scan_id)
        db.execute(f"UPDATE scans SET {', '.join(sets)} WHERE id = ?", params)


class ProjectStore:
    def upsert(self, summary: ProjectSummary) -> None:
        elementor = summary.elementor.elementor in ("detected",) or any(
            "elementor" in (p.slug or "").lower() for p in summary.plugins
        )
        db.execute(
            "INSERT INTO projects (owner, repo, full_name, branch, summary_json,"
            " scanned_at, file_count, is_wordpress, has_elementor)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(owner, repo) DO UPDATE SET"
            "  full_name=excluded.full_name, branch=excluded.branch,"
            "  summary_json=excluded.summary_json, scanned_at=excluded.scanned_at,"
            "  file_count=excluded.file_count, is_wordpress=excluded.is_wordpress,"
            "  has_elementor=excluded.has_elementor",
            (
                summary.owner,
                summary.repo,
                summary.repository,
                summary.branch,
                summary.model_dump_json(),
                summary.scanned_at.isoformat(),
                summary.total_files,
                1 if summary.is_wordpress else 0,
                1 if elementor else 0,
            ),
        )

    def get(self, owner: str, repo: str) -> ProjectSummary | None:
        row = db.query_one(
            "SELECT summary_json FROM projects WHERE owner = ? AND repo = ?",
            (owner, repo),
        )
        if row is None:
            return None
        return ProjectSummary.model_validate_json(row["summary_json"])

    def list(self) -> list[ProjectSummary]:
        rows = db.query_all("SELECT summary_json FROM projects ORDER BY scanned_at DESC")
        summaries: list[ProjectSummary] = []
        for row in rows:
            try:
                summaries.append(ProjectSummary.model_validate_json(row["summary_json"]))
            except Exception:
                continue
        return summaries

    def delete(self, owner: str, repo: str) -> None:
        db.execute("DELETE FROM projects WHERE owner = ? AND repo = ?", (owner, repo))


def scan_status_from_row(row: dict[str, Any]) -> ScanStatus:
    stages_raw = row.get("stages_json")
    stages: list[StageStatus] = []
    if stages_raw:
        try:
            stages = [StageStatus.model_validate(item) for item in json.loads(stages_raw)]
        except Exception:
            stages = []
    from backend.utils.helpers import parse_iso

    return ScanStatus(
        scan_id=row["id"],
        owner=row["owner"],
        repo=row["repo"],
        status=row["status"],
        progress=float(row.get("progress") or 0.0),
        stages=stages,
        error=row.get("error"),
        error_details=row.get("error_details"),
        branch=row.get("branch"),
        started_at=parse_iso(row.get("started_at")),
        finished_at=parse_iso(row.get("finished_at")),
    )


class ChatStore:
    def append_messages(
        self, owner: str, repo: str, conversation_id: str | None, messages: list[ChatMessage]
    ) -> None:
        now = iso()
        for message in messages:
            db.execute(
                "INSERT INTO chat_messages (conversation_id, owner, repo, role, content,"
                " created_at) VALUES (?,?,?,?,?,?)",
                (conversation_id, owner, repo, message.role, message.content[:8000], now),
            )

    def save_analysis(
        self,
        *,
        owner: str,
        repo: str,
        conversation_id: str | None,
        question: str,
        analysis: AnalysisResponse,
    ) -> str:
        result_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO analysis_results (id, conversation_id, owner, repo, question,"
            " result_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                result_id,
                conversation_id,
                owner,
                repo,
                question[:4000],
                analysis.model_dump_json(),
                iso(),
            ),
        )
        return result_id

    def recent_for(self, owner: str, repo: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = db.query_all(
            "SELECT role, content, created_at FROM chat_messages"
            " WHERE owner = ? AND repo = ? ORDER BY id DESC LIMIT ?",
            (owner, repo, limit),
        )
        return [dict(r) for r in reversed(rows)]
