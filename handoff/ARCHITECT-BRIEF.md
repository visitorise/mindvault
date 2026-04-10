# ARCHITECT-BRIEF — MindVault

## Step 6 — SKILL.md 완성 + 배포 준비

**Goal**: Claude Code에서 `/mindvault`로 호출 시 완전한 파이프라인이 돌아가는 Skill 정의 + README + end-to-end 검증 + GitHub 초기화.

**Scope**: skill/SKILL.md 재작성, README.md 보강, end-to-end 테스트, git init + 첫 커밋

---

### 6.1 skill/SKILL.md — 완전한 Skill 정의

Graphify SKILL.md 수준으로 작성. Claude Code가 이 파일을 읽고 자율적으로 파이프라인을 실행할 수 있어야 함.

**구조**:

```markdown
# /mindvault

Turn any folder into a searchable knowledge base with a graph, wiki, and BM25 index.
Three layers: Search (zero tokens) → Graph (relationships) → Wiki (context).

## Usage

/mindvault .                           # full pipeline on current directory
/mindvault <path>                      # full pipeline on specific path
/mindvault query "<question>"          # 3-layer unified query
/mindvault query "<question>" --dfs    # trace a specific chain
/mindvault ingest <path>               # add new files, incremental update
/mindvault lint                        # check wiki + graph consistency
/mindvault status                      # show current state
/mindvault watch                       # auto-update on file changes

## What MindVault does

[2~3문단으로 핵심 가치 설명:
- 토큰 절약 (질의당 ~900 토큰 vs 원본 읽기 60,000+)
- 세션 연속성 (위키에 Why/How가 축적, 새 세션에서 재설명 불필요)
- 완전 자동 (git hook + Claude Code hook으로 자동 갱신)]

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.

### Step 1 — Ensure mindvault is installed
[pip install 확인 + python interpreter 감지]

### Step 2 — Run the pipeline
[pipeline.run() 호출 — detect → extract_ast → build_graph → cluster → analyze → wiki → index]

### Step 3 — Report results
[God Nodes, Surprising Connections, Suggested Questions 출력]
[가장 흥미로운 질문으로 탐색 유도]

## For /mindvault query
[query.py 호출 — search → graph → wiki 3-layer]
[결과 포맷: Search Results → Graph Context → Wiki Context]

## For /mindvault lint
[lint_wiki + lint_graph 실행, 결과 출력]

## For /mindvault status
[mindvault-out/ 상태 확인, 노드/엣지/위키 수 출력]

## For /mindvault ingest
[새 파일 추가 → run_incremental]

## Outputs
mindvault-out/
  graph.json          — raw graph data
  graph.html          — interactive visualization
  GRAPH_REPORT.md     — audit report
  wiki/INDEX.md       — wiki entry point
  wiki/*.md           — community pages
  search_index.json   — BM25 index
```

**Flag**: SKILL.md는 Claude가 자율적으로 읽고 실행하는 지시서임. bash 코드 블록으로 실행 방법을 명시적으로 제공해야 함. Graphify SKILL.md의 패턴을 참고하되, MindVault의 3-layer 구조에 맞게 작성.

---

### 6.2 README.md — PyPI 배포용

```markdown
# MindVault

Turn any folder into a searchable knowledge base.

## Install
pip install mindvault
mindvault install

## Quick Start
[3줄로 핵심 사용법]

## How It Works
[3-Layer 다이어그램]

## Commands
[CLI 명령어 표]

## Token Savings
[벤치마크 수치]

## License
MIT
```

---

### 6.3 End-to-End 테스트

MindVault 소스코드 자체에 대해 전체 파이프라인을 돌리고 검증:

```bash
# Clean slate
rm -rf /Users/yonghaekim/my-folder/apps/mindvault/mindvault-out

# E2E Test 1: Full pipeline via CLI
cd /Users/yonghaekim/my-folder/apps/mindvault
mindvault ingest src

# E2E Test 2: Query via CLI
mindvault query "how does the search layer work"

# E2E Test 3: Status
mindvault status

# E2E Test 4: Lint
mindvault lint

# E2E Test 5: Install (skill registration)
mindvault install

# Verify all outputs exist
ls -la mindvault-out/
ls mindvault-out/wiki/
cat mindvault-out/GRAPH_REPORT.md | head -30
```

---

### 6.4 Git 초기화

```bash
cd /Users/yonghaekim/my-folder/apps/mindvault
git init
```

**.gitignore** 생성:
```
__pycache__/
*.egg-info/
dist/
build/
*.pyc
.venv/
mindvault-out/
*.egg
.eggs/
```

첫 커밋:
```
feat: MindVault v0.1.0 — 3-layer knowledge management tool

Search (BM25) + Graph (NetworkX + tree-sitter) + Wiki (auto-generated)
Token savings: ~60x per query vs reading raw files
```

**Flag**: git push는 하지 않음. 사용자가 GitHub repo를 만든 후 직접 push.

---

### 6.5 Acceptance Criteria

1. `skill/SKILL.md`가 `/mindvault .` 실행에 충분한 지시서인가
2. `mindvault install` → skill 등록 + git hook 설치 성공
3. `mindvault ingest src` → mindvault-out/ 에 모든 출력 파일 생성
4. `mindvault query "search"` → 3-layer 결과 출력
5. `mindvault status` → 상태 표시
6. `mindvault lint` → 정합성 결과
7. README.md가 PyPI 배포에 적합한 수준
8. .gitignore + git init + 첫 커밋 완료
