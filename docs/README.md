# Synapse Memory 문서

작성자: JunyoungJung  
작성일: 2026-05-13

이 문서는 Synapse Memory를 처음 쓰는 사람이 길을 잃지 않도록 읽는 순서를 정리합니다.
세부 구현 설명보다 "왜 필요하고, 어떻게 시작하고, 매일 무엇을 하면 되는지"를 먼저
따라가게 구성했습니다.

## 읽는 순서

1. [처음부터 끝까지 사용하기](start-here.md)

   설치 후 첫 질문까지 이어지는 기본 흐름입니다. Synapse Memory가 무엇을 모으고,
   어디에 저장하고, 어떤 명령으로 다시 꺼내 쓰는지 순서대로 설명합니다.

2. [개인정보, 비용, 삭제](privacy-and-cost.md)

   원본 자료가 어디에 남는지, 외부 AI로 무엇이 나가는지, 비용이 드는 작업은 무엇인지,
   완전히 지우려면 무엇을 지우면 되는지 정리합니다.

3. [명령과 문제 해결](reference.md)

   Claude Code slash 명령, Codex skill 요청, CLI 명령, 설정 변경, 환경 복구 방법만
   모았습니다. v0.9.0 이후 추가된 흐름도 같은 문서에 정리돼 있습니다.

   - 기존 vault를 새 폴더 구조로 옮기기 (`migrate-folders`, v0.9.0)
   - 개인 메모를 외부 AI에 안전 전달 (`/sm:redact`, v0.10.0)
   - 다른 프로젝트에서 sm 컨텍스트 활용 (`/sm:setup`, `/sm:sync`, v0.11.0)
   - Profile 후보 GUI 승인 (`/sm:apply-profile`, v0.12.0)
   - Obsidian Graph 시각화 (`/sm:moc` + `node/*` 태그, v0.13.0)

## 한 문장으로 이해하기

Synapse Memory는 내 Mac 안에서 새 노트와 AI 작업 기록을 정리해 요약 카드를 만들고,
외부 AI에는 원본 대신 안전한 카드와 승인된 자료만 보내 답을 받는 도구입니다.

## 어디부터 시작해야 하나요?

처음이라면 바로 [처음부터 끝까지 사용하기](start-here.md)를 읽으면 됩니다. 이미 설치를
마쳤다면 Claude Code에서는 `/sm:doctor`, `/sm:daily`, `/sm:ask`를 먼저 기억하면
충분합니다. Codex TUI에서는 `$doctor`, `$daily`, `$ask`처럼 `$`로 skill을 검색하고
실행합니다.
