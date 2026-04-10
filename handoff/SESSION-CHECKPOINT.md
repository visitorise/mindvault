# SESSION-CHECKPOINT — MindVault

**Last updated**: 2026-04-10
**Current step**: Step 0 — Project Setup
**Status**: Three Man Team 세팅 완료, Architect 첫 설계 대기 중

## Context
- PyPI 패키지명 `mindvault` 사용 가능 확인
- 3-Layer 아키텍처: Search + Graph + Wiki
- 독립 패키지 (graphify, qmd 의존 없음)
- 자동 갱신 필수 (git hook, Claude Code hook, 파일 감시)

## 핵심 목표
1. 토큰 절약 — 질의당 ~900 토큰
2. 세션 연속성 — 새 세션에서 재설명 불필요
3. 완전 자동 — 사용자 개입 없이 갱신

## 참고 도구
- Karpathy LLM Wiki 패턴
- safishamsi/graphify (그래프 레이어 참고)
- ussumant/llm-wiki-compiler (위키 레이어 참고, 90% 토큰 절감)
- qmd (검색 레이어 참고)

## Next
Arch가 Step 1 설계: 프로젝트 스켈레톤 + 모듈 인터페이스 정의
