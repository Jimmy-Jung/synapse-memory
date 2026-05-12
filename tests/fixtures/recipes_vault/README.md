# `recipes_vault` fixture

`007-me-recipes` 단위 테스트에서 사용하는 임시 vault 트리.

## 기본 layout (T020 에서 채움)

```
recipes_vault/
├── 10_Journal/Drafts/                    # journal recipe 의 save_subpath
├── 20_Reference/
│   ├── Projects/
│   │   ├── prj-2026-w19-alpha.md         # ProjectCard 1
│   │   └── prj-2026-w19-beta.md          # ProjectCard 2
│   └── Companies/
│       └── acme_co.md                    # CompanyCard (US2 시나리오)
├── 30_Creative/
│   ├── Reports/                          # weekly_report save_subpath (empty)
│   ├── Brainstorms/                      # brainstorm save_subpath (empty)
│   └── Drafts/                           # resume save_subpath (empty)
├── 90_System/AI/
│   ├── Profile.md                        # frontmatter: preferred_lang, domain
│   ├── DecisionPatterns.md
│   └── recipes/                          # 사용자 recipe (US3 fixture variant)
└── diary.md                              # US3 user recipe sample
```

## Profile.md frontmatter variants

- `profile_default/Profile.md` — frontmatter 없음 → fallback (한국어/generic)
- `profile_en_design/Profile.md` — `preferred_lang: en, domain: design`
- `profile_en_research/Profile.md` — `preferred_lang: en, domain: research`

variant 는 T032 에서 디렉터리로 분기.

본 fixture 는 stateless — 각 테스트가 `tmp_path` 로 복제해서 변경한다. 원본 디렉터리는
변경되지 않는다.
