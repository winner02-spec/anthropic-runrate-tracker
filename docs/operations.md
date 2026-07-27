# 운영 가이드

## 수집 운영
- 주 수집 방식: **Mac launchd** (수집 3시간 간격 + 매일 08:30 KST 전체 재검증).
  - `launchd/com.anthropic-runrate.collect.plist`, `com.anthropic-runrate.daily-verify.plist`
  - 등록은 **사용자 승인 후**: `launchctl load ~/Library/LaunchAgents/<plist>` (전제: `.venv` 생성)
- 보조: GitHub Actions `collect.yml`(기본 비활성, repo Variable `ENABLE_SCHEDULED_COLLECT=true` 로 활성).
- 수동: `python -m tracker collect`.

## 검토 절차
1. `python -m tracker collect` → 자동확정(Tier A 명확) 외에는 `needs_review` + review_queue.
2. `python -m tracker review` 로 후보 확인(발견 표현·기준일·발표일·출처·근거·신뢰도).
3. 검증 후 `approve <id>` 또는 `reject <id>`. 승인 시 dashboard.json 자동 갱신.
4. Tier D(X 등)는 원출처 확인 후에만 승격.

## 장애 처리
- 소스/문서별 예외 격리 → 하나 실패해도 나머지 계속. 오류는 `logs/` 및 `ingestion_runs.errors` 에 기록.
- 특정 사이트 HTML 구조 변경 → 해당 파서(`tracker/collectors/*`)만 실패. 파서만 수정.
- 대시보드가 비면: `python -m tracker status` 로 확정 수 확인 → `export` 재실행.
- Telegram 실패: 키/네트워크 확인. 미설정이면 dry-run 으로 정상(수집·대시보드 영향 없음).

## 백업과 복구
- 원본 DB: `database/runrate.sqlite` (gitignore, 배포 안 함). 정기적으로 파일 복사 백업 권장.
- 정적 산출물: `frontend/public/data/dashboard.json` (커밋본). 손상 시 DB 에서 `export` 로 재생성.
- 스키마 변경 시 `tracker/database/schema.py` 의 `SCHEMA_VERSION` 을 올리고 migration·문서 갱신.

## 배포 절차
1. `python -m tracker export` (또는 daily-verify) 로 `dashboard.json` 최신화.
2. 변경 커밋 → `main` push → GitHub Actions `deploy.yml` 가 `frontend` 빌드 후 Pages 배포.
3. **DB·.env 는 절대 커밋/배포하지 않음** (.gitignore 로 강제).
4. 실제 push/배포·launchd 등록·Telegram 실발송은 사용자 승인 후.

## 점검 명령
```sh
python -m tracker status                          # 확정/검토/최근수집 현황
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
pytest -q                                         # 백엔드 테스트(3.11+)
plutil -lint launchd/*.plist                      # launchd 문법
```
