# ARCHITECT-BRIEF — MindVault

## Step 12 — 문서 구조 추출 (Document Structure Extraction)

**Goal**: 2단계(Extract)에서 코드뿐 아니라 마크다운/텍스트/PDF의 구조도 추출. LLM 없이, 토큰 0으로 문서의 골격을 그래프 노드/엣지로 변환.

**Scope**: extract.py 확장

---

### 12.1 extract.py — extract_document_structure 추가

```python
def extract_document_structure(doc_files: list[Path]) -> dict:
    """문서 파일에서 구조를 추출 (LLM 불필요, 토큰 0).
    
    Returns: {nodes: [], edges: [], input_tokens: 0, output_tokens: 0}
    """
```

**마크다운 (.md) 추출:**
- `#` 헤더 계층 → 노드 (depth 1/2/3)
- 헤더 간 parent-child 관계 → `contains` 엣지
- `[링크](url)` → `references` 엣지 (같은 프로젝트 내 파일이면)
- `` ```코드블록``` `` → `has_code_example` 엣지 (언어 태그가 있으면 해당 언어 노드 생성)
- `[[wikilink]]` → `references` 엣지

**텍스트 (.txt, .rst) 추출:**
- 줄 패턴으로 섹션 감지 (빈 줄로 구분된 블록, 대문자 줄 = 제목)
- RST의 `===` / `---` 밑줄 헤더 → 노드

**PDF (.pdf) 추출:**
- `pdftotext`로 텍스트 추출 시도
- 없으면 skip (에러 아님)
- 추출된 텍스트에서 대문자/숫자 시작 줄을 섹션 헤더로 추정

**노드 ID 규칙**: `{filestem}_{heading_slug}` (소문자, 공백→언더스코어)
**노드 스키마**: 기존 코드 노드와 동일
```python
{"id": str, "label": str, "file_type": "document", "source_file": str, "source_location": "line N"}
```

**엣지 스키마**: 
```python
{"source": str, "target": str, "relation": "contains|references|has_code_example", 
 "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": str}
```

---

### 12.2 compile.py — 문서 구조 추출을 파이프라인에 통합

현재:
```python
ast_result = extract_ast(code_files)
sem_result = extract_semantic(doc_files, output_dir)
extraction = merge_extractions(ast_result, sem_result)
```

변경:
```python
ast_result = extract_ast(code_files)
doc_result = extract_document_structure(doc_files)  # NEW
sem_result = extract_semantic(doc_files, output_dir)
extraction = merge_extractions(ast_result, doc_result, sem_result)  # 3-way merge
```

`_merge_extractions`을 2개→가변 인자로 확장.

---

### 12.3 테스트 시나리오

```bash
# Test 1: 마크다운 구조 추출
python3 -c "
from mindvault.extract import extract_document_structure
from pathlib import Path
result = extract_document_structure([Path('/Users/yonghaekim/my-folder/apps/mindvault/README.md')])
print(f'Nodes: {len(result[\"nodes\"])}, Edges: {len(result[\"edges\"])}')
for n in result['nodes'][:5]:
    print(f'  {n[\"id\"]}: {n[\"label\"]}')
assert len(result['nodes']) > 5, 'README should have many sections'
assert result['input_tokens'] == 0, 'Should use 0 tokens'
print('Test 1: PASS')
"

# Test 2: 전체 파이프라인에 통합 확인
python3 -c "
from mindvault.pipeline import run
from pathlib import Path
import shutil
out = Path('/Users/yonghaekim/my-folder/apps/mindvault/mindvault-out')
if out.exists(): shutil.rmtree(out)
result = run(Path('/Users/yonghaekim/my-folder/apps/mindvault'), out)
print(f'Nodes: {result[\"nodes\"]}, Edges: {result[\"edges\"]}')
# Should have more nodes than before (code + document structure)
assert result['nodes'] > 100, 'Should include doc structure nodes'
print('Test 2: PASS')
"

# Test 3: 빈 문서 처리
python3 -c "
from mindvault.extract import extract_document_structure
from pathlib import Path
import tempfile
with tempfile.NamedTemporaryFile(suffix='.md', mode='w', delete=False) as f:
    f.write('')
    f.flush()
    result = extract_document_structure([Path(f.name)])
    print(f'Empty doc: {len(result[\"nodes\"])} nodes')
    print('Test 3: PASS')
"
```

---

### 12.4 Constraints

- LLM 호출 없음 — 순수 파싱만
- `input_tokens`와 `output_tokens`는 항상 0
- PDF에서 `pdftotext` 없으면 조용히 skip
- 기존 extract_ast, extract_semantic과 독립적으로 동작
- `_merge_extractions`에서 노드 ID 중복 시 첫 번째 유지 (기존 동작과 동일)

### 12.5 Acceptance Criteria

1. README.md에서 5개+ 섹션 노드 추출
2. 토큰 사용량 0
3. 파이프라인에 통합되어 전체 노드 수 증가
4. 빈 문서 처리 시 에러 없음
5. 3개 테스트 모두 PASS
