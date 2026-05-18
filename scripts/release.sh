#!/usr/bin/env bash
# Synapse Memory 릴리즈 워크플로 — release branch initializer.
#
# 사용:  ./scripts/release.sh <new-version>
# 예:    ./scripts/release.sh 0.8.6
#
# 흐름:
#   1) main 브랜치 / 클린 상태 검증 + origin/main 동기화
#   2) release/<new-version> 브랜치 생성
#   3) pyproject.toml, __init__.py, README.md, CHANGELOG.md 자동 bump
#   4) commit + push + PR 생성
#   5) PR 에서 .github/workflows/release-check.yml 가 검증
#      merge 시 .github/workflows/release-publish.yml 가
#      tag + GitHub Release 를 자동 생성
#
# CHANGELOG 본문 (TODO 자리) 만 수동 작성하면 된다.
#
# 저자: Synapse Memory Maintainers

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <new-version>" >&2
  exit 2
fi

new="$1"
if ! [[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must be X.Y.Z (got: $new)" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)"

current_branch=$(git branch --show-current)
if [[ "$current_branch" != "main" ]]; then
  echo "Must run from 'main' branch (current: $current_branch)" >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree has uncommitted changes. Commit/stash first." >&2
  exit 1
fi

git fetch origin main --quiet
if ! git merge-base --is-ancestor origin/main HEAD; then
  echo "Local main is behind origin/main. Run 'git pull' first." >&2
  exit 1
fi

branch="release/${new}"
if git show-ref --verify --quiet "refs/heads/${branch}"; then
  echo "Branch ${branch} already exists locally." >&2
  exit 1
fi
if git ls-remote --exit-code --heads origin "${branch}" >/dev/null 2>&1; then
  echo "Branch ${branch} already exists on origin." >&2
  exit 1
fi

old=$(awk -F'"' '/^version = /{print $2; exit}' pyproject.toml)
if [[ -z "$old" ]]; then
  echo "Failed to read current version from pyproject.toml" >&2
  exit 1
fi
if [[ "$old" == "$new" ]]; then
  echo "pyproject.toml is already at v${new}." >&2
  exit 1
fi

today=$(date +%Y-%m-%d)
init_file="src/synapse_memory/__init__.py"

git checkout -b "${branch}"

# 1) pyproject.toml
sed -i '' -E "s/^version = \"${old}\"/version = \"${new}\"/" pyproject.toml

# 2) __init__.py
sed -i '' -E "s/^__version__ = \"[^\"]+\"/__version__ = \"${new}\"/" "$init_file"

# 3) README.md installer 링크
sed -i '' -E "s|releases/download/v${old}/SynapseMemory-v${old}|releases/download/v${new}/SynapseMemory-v${new}|g" README.md
sed -i '' -E "s|SynapseMemory-v${old}-macos-installer\.zip|SynapseMemory-v${new}-macos-installer.zip|g" README.md

# 4) plugin manifest version (Claude Code / Codex 플러그인 설정 화면 표시)
#    pyproject 와 같은 값으로 강제 — 이전 값이 drift 되어 있어도 무조건 new 로 정렬.
for manifest in .claude-plugin/plugin.json .codex-plugin/plugin.json; do
  if [[ -f "$manifest" ]]; then
    python3 - "$manifest" "$new" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
new = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
if data.get("version") == new:
    sys.exit(0)
data["version"] = new
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  fi
done

# 5) CHANGELOG stub
python3 - "$new" "$today" <<'PY'
import pathlib
import sys

new, today = sys.argv[1], sys.argv[2]
path = pathlib.Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
marker = "All notable changes to Synapse Memory are documented here.\n\n"
if marker not in text:
    print("CHANGELOG marker not found — leaving file untouched", file=sys.stderr)
    sys.exit(1)
if f"## [{new}]" in text:
    print(f"CHANGELOG already contains [{new}] section — leaving untouched", file=sys.stderr)
    sys.exit(0)
stub = (
    f"## [{new}] — {today}\n\n"
    "### Fixed\n\n"
    "- TODO: 변경 내역 작성 (release-check 가 TODO 잔존 시 실패시킴)\n\n"
)
path.write_text(text.replace(marker, marker + stub, 1), encoding="utf-8")
PY

git add pyproject.toml "$init_file" README.md CHANGELOG.md \
  .claude-plugin/plugin.json .codex-plugin/plugin.json
git commit -m "release: bump v${old} → v${new}"
git push -u origin "${branch}"

if command -v gh >/dev/null 2>&1; then
  gh pr create \
    --base main \
    --head "${branch}" \
    --title "release: v${new}" \
    --body "$(cat <<EOF
## v${new}

\`release.sh\` 로 자동 생성된 릴리즈 PR.

### Checklist

- [ ] CHANGELOG.md \`[${new}]\` 섹션 본문 작성 (TODO 항목 제거)
- [ ] release-check workflow 통과 (버전 일치, 문서, pytest)
- [ ] merge 후 release-publish workflow 가 \`v${new}\` tag + Release 자동 publish 됨을 확인

### 자동 검증 항목 (release-check.yml)

- 브랜치명 \`release/${new}\` ↔ \`pyproject.toml\` version ↔ \`__version__\` 일치
- README installer 링크가 \`v${new}\` 를 가리킴
- CHANGELOG \`[${new}]\` 섹션이 비어있지 않고 TODO 미잔존
- pytest 전체 통과
EOF
)"
else
  cat <<MSG

⚠️  gh CLI 가 없습니다. PR 을 직접 생성하세요:
   https://github.com/Jimmy-Jung/synapse-memory/compare/main...${branch}?expand=1
MSG
fi

cat <<MSG

✅ v${old} → v${new} 릴리즈 브랜치 준비 완료
   브랜치: ${branch}
   다음:
     1) CHANGELOG.md 의 [${new}] TODO 본문 작성
        git commit -am "docs: fill CHANGELOG for v${new}"
        git push
     2) PR 의 release-check workflow 가 모두 green 인지 확인
     3) PR merge → release-publish workflow 가 tag + Release 자동 생성
MSG
