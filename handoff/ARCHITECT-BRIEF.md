# ARCHITECT-BRIEF — MindVault

## Step 13 — Rules Engine (Phase 2 하네스 엔지니어링)

**Goal**: 프로젝트별 규칙을 정의하고, AI가 규칙을 위반하려 할 때 시스템 레벨에서 강제로 경고를 주입하는 Rules Engine. Phase 1(Lore)의 기록이 실제로 참조되도록 강제하는 메커니즘.

**배경**: Phase 1에서 Lore 시스템(결정/실패 자동 기록)을 구현했지만, AI가 lore를 무시하고 같은 실수를 반복할 수 있음. Rules Engine이 있어야 "기억하는 AI"에서 "규칙을 따르는 AI"로 업그레이드됨.

**Scope**: 새 모듈 `rules.py` + CLI 확장 + PostToolUse hook 통합

---

### 13.1 rules.py — 핵심 모듈

**규칙 저장소**: `mindvault-out/rules.yaml` (프로젝트별) 또는 `~/.mindvault/rules.yaml` (글로벌)

```yaml
# mindvault-out/rules.yaml
version: 1
rules:
  - id: no-redis-cache
    trigger: "redis|Redis|REDIS"
    type: warn
    message: "Redis 캐시는 이전에 위젯 동기화 충돌로 롤백됨 (Lore 참조). SQLite 캐시를 사용할 것."
    lore_ref: "2026-04-14-redis.md"
    
  - id: test-before-pr
    trigger: "git push|gh pr create"
    type: block
    message: "PR 생성 전 반드시 테스트를 실행하세요: pytest tests/"
    
  - id: no-edit-config
    trigger: "Edit.*config\\.production"
    type: block
    message: "프로덕션 설정 파일을 직접 수정하지 마세요."

  - id: check-lore-before-architecture
    trigger: "restructur|refactor|migrate|아키텍처"
    type: warn  
    message: "아키텍처 변경 전 관련 Lore 기록을 확인하세요: mindvault lore search --query '...'"
```

**규칙 스키마:**
```python
{
    "id": str,           # 고유 ID
    "trigger": str,      # 정규식 패턴 (도구 입력/출력과 매칭)
    "type": "warn" | "block",  # warn=경고 주입, block=실행 차단 제안
    "message": str,      # AI에게 주입할 메시지
    "lore_ref": str | None,  # 관련 Lore 항목 (선택)
    "scope": "command" | "output" | "both",  # 매칭 대상 (기본: both)
    "enabled": bool,     # 활성화 여부 (기본: true)
}
```

**함수:**
```python
def load_rules(output_dir: Path) -> list[dict]
    """프로젝트 + 글로벌 규칙 로드. 프로젝트 규칙이 우선."""

def check_rules(text: str, rules: list[dict], context: str = "both") -> list[dict]
    """텍스트에서 규칙 위반 감지. 매칭된 규칙 리스트 반환."""

def add_rule(output_dir: Path, rule_id: str, trigger: str, rule_type: str, message: str, lore_ref: str = None) -> Path
    """규칙 추가. rules.yaml에 append."""

def remove_rule(output_dir: Path, rule_id: str) -> bool
    """규칙 제거."""

def list_rules(output_dir: Path) -> list[dict]
    """모든 활성 규칙 목록."""
```

---

### 13.2 PostToolUse hook 통합

기존 `mindvault-lore-hook.sh`를 확장하거나 새 `mindvault-rules-hook.sh` 생성.

**동작 흐름:**
1. AI가 Bash/Edit/Write 도구 사용
2. hook이 stdin JSON에서 command + stdout + stderr 추출
3. `mindvault rules check "텍스트"` 실행
4. 매칭된 규칙이 있으면:
   - `warn` → `<rules-warning>` 태그로 경고 주입
   - `block` → `<rules-block>` 태그로 차단 제안 주입

**출력 예시:**
```
<rules-warning>
Rule: no-redis-cache
Redis 캐시는 이전에 위젯 동기화 충돌로 롤백됨 (Lore 참조). SQLite 캐시를 사용할 것.
Related lore: mindvault lore search --query "redis"
</rules-warning>
```

**중요**: hook은 도구 실행을 실제로 차단하지 않음 (Claude Code hook은 차단 권한 없음). `block` 타입도 강력한 경고를 주입할 뿐. AI가 판단해서 사용자에게 알리는 구조.

---

### 13.3 CLI 확장

```
mindvault rules add --id "rule-id" --trigger "pattern" --type warn --message "메시지"
mindvault rules remove --id "rule-id"
mindvault rules list
mindvault rules check "텍스트"   # 수동 테스트용
```

**mindvault install에 통합:**
- 설치 시 rules hook 자동 등록 (lore hook과 동일 패턴)
- 기본 규칙 없음 — 사용자가 직접 추가하거나 lore 기반 자동 제안

---

### 13.4 Lore → Rules 자동 제안

Lore 항목이 기록될 때, 관련 규칙을 자동 제안:

```
<lore-rule-suggestion>
방금 기록된 Lore: "Redis 캐시 롤백"
이 실수를 방지하는 규칙을 추가할까요?
mindvault rules add --id "no-redis" --trigger "redis" --type warn --message "Redis는 위젯 충돌 이력 있음"
</lore-rule-suggestion>
```

이것도 Lore의 lazy onboarding과 동일 패턴 — 자동 기록이 아니라 제안 후 사용자 승인.

---

### 13.5 테스트 시나리오

1. rules.yaml 파싱 + 규칙 로드
2. 텍스트에서 규칙 매칭 (정규식)
3. warn/block 구분 동작
4. 프로젝트 규칙이 글로벌 규칙보다 우선
5. CLI add/remove/list/check 동작
6. hook 통합 — Bash 출력에서 규칙 위반 감지
7. Lore → Rules 제안 동작
8. 빈 규칙 파일 처리
9. 잘못된 정규식 처리 (에러 안 남)
10. enabled: false인 규칙 무시

---

### 13.6 Constraints

- YAML 파서: PyYAML 의존성 추가 필요 (pyproject.toml). 없으면 JSON 폴백
- hook 성능: 규칙 체크는 1초 이내 (정규식 매칭만, LLM 없음)
- 기존 lore hook과 충돌 없어야 함 — 별도 hook이거나 기존 hook 확장
- Claude Code 전용 아닌 기능도 있어야 함 (CLI `rules check`는 어디서든 사용 가능)

### 13.7 Acceptance Criteria

1. `mindvault rules add` → rules.yaml에 규칙 추가됨
2. `mindvault rules check "redis 설치"` → 매칭된 규칙 출력
3. PostToolUse hook에서 규칙 위반 시 `<rules-warning>` 주입
4. Lore 기록 시 규칙 제안 출력
5. 10개 테스트 전부 PASS
6. 기존 160개 테스트 깨지지 않음
