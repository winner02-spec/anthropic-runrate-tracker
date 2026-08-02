#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""일회성 migration — anomaly_queue 정리(삭제 없음).

1) company_id 오분류 정정: 레거시 일괄 backfill(company_id NULL → anthropic)로 잘못 채워진 행을
   **연결 observation 재확인**(health.resolve_anomaly_owner)으로 정정. 변경 전 값은 audit_json 에 보존.
2) 중복 누적 정리: 같은 원인·같은 observation 을 재계산 때마다 새 행으로 쌓은 건을
   최신 1건만 open 으로 두고 이전 행은 superseded(reason=duplicate_recompute) 로 남긴다.

사용:  python scripts/migrate_anomaly_ownership.py [--dry-run]
재실행해도 안전(멱등).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import config, health          # noqa: E402
from tracker.database import db             # noqa: E402


def _dup_groups(conn) -> dict[tuple, list[dict]]:
    """open 레코드를 '같은 이상'으로 묶는다.
    묶음 기준 = (company_id, anomaly_type, 기준 observation 조합).
    observation 조합은 재계산으로 얻은 anomaly_key 를 우선 쓰고,
    key 가 없는 레거시 행은 detail 에서 뽑은 값·날짜 지문으로 대체한다."""
    groups: dict[tuple, list[dict]] = {}
    for r in db.fetchall(conn, "SELECT * FROM anomaly_queue WHERE status='open' ORDER BY id"):
        d = dict(r)
        if d.get("anomaly_key"):
            gkey = (d["company_id"], d["anomaly_type"], d["anomaly_key"])
        else:
            gkey = (d["company_id"], d["anomaly_type"], health.legacy_detail_fingerprint(d))
        groups.setdefault(gkey, []).append(d)
    return groups


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(str(config.DB_PATH))
    db.init_db(conn)

    print("① company_id 오분류 정정 (연결 observation 재확인)")
    for res in health.correct_anomaly_ownership(conn, dry_run=args.dry_run):
        if res["action"] == "corrected":
            print(f"  #{res['id']} {res['from']} → {res['to']}({res['slug']}) · 근거 "
                  f"{json.dumps(res['evidence'], ensure_ascii=False)}")
        else:
            print(f"  #{res['id']} {res['action']}"
                  + (f" ({res.get('reason')})" if res.get("reason") else ""))

    print("② 중복 누적 정리 (최신 1건만 open, 이전 건은 superseded)")
    for gkey, rows in _dup_groups(conn).items():
        if len(rows) < 2:
            continue
        keep = rows[-1]      # id 오름차순 → 마지막이 최신 탐지
        for old in rows[:-1]:
            print(f"  #{old['id']} → superseded by #{keep['id']} · {old['anomaly_type']} · {old['detail']}")
            if not args.dry_run:
                health.supersede_anomaly(conn, old["id"], keep["id"], "duplicate_recompute")

    for status in ("open", "dismissed", "superseded"):
        n = db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue WHERE status=?", (status,))[0]
        print(f"  {status}: {n}건")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
