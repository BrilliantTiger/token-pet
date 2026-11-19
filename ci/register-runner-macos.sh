#!/bin/bash
# self-hosted 러너를 이 Mac 에 등록한다 (TOK-62). **대표님 PC 에 프로그램을 깔고 로그인 항목을 만든다 —
# 대표님이 확인한 뒤에만 돌린다.** 절차와 먼저 바꿔야 하는 저장소 설정은 ci/SELF_HOSTED_RUNNERS.md.
#
#   ci/register-runner-macos.sh            등록 + 로그인 항목(LaunchAgent)으로 시작
#   ci/register-runner-macos.sh remove     서비스 내리고 등록 해제
#
# 러너는 **로그인한 사용자의 LaunchAgent** 로 돈다(svc.sh). 데몬으로 돌리면 사용자의 키체인과 CLI
# 로그인 상태를 볼 수 없어 실기기 잡의 뜻이 없어진다.
# source 로 불러도 아무것도 하지 않는다 — 등록은 실행했을 때만.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0
set -euo pipefail

REPO="BrilliantTiger/token-pet"
DIR="$HOME/actions-runner-token-pet"
NAME="$(scutil --get LocalHostName 2>/dev/null || hostname -s)"

command -v gh >/dev/null || { echo "gh CLI 가 필요합니다"; exit 1; }

if [ "${1:-}" = "remove" ]; then
  cd "$DIR"
  ./svc.sh stop || true
  ./svc.sh uninstall || true
  ./config.sh remove --token "$(gh api -X POST "repos/$REPO/actions/runners/remove-token" --jq .token)"
  gh variable delete SELF_HOSTED_MACOS --repo "$REPO" || true
  echo "해제했습니다. 폴더는 남아 있습니다: $DIR"
  exit 0
fi

# 포크 PR 이 승인 없이 워크플로를 돌릴 수 있으면 등록하지 않는다 — 공개 저장소다.
policy="$(gh api "repos/$REPO/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy)"
if [ "$policy" != "all_external_contributors" ]; then
  echo "❌ 포크 PR 승인 정책이 '$policy' 입니다. 먼저 all_external_contributors 로 바꾸세요:"
  echo "   gh api -X PUT repos/$REPO/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors"
  exit 1
fi

case "$(uname -m)" in
  arm64) ARCH=arm64 ;;
  x86_64) ARCH=x64 ;;
  *) echo "모르는 아키텍처: $(uname -m)"; exit 1 ;;
esac
VER="$(gh api repos/actions/runner/releases/latest --jq .tag_name | sed 's/^v//')"
PKG="actions-runner-osx-$ARCH-$VER.tar.gz"
SHA="$(gh api repos/actions/runner/releases/latest --jq .body | grep -A1 "$PKG" | grep -oE '[0-9a-f]{64}' | head -1)"
[ -n "$SHA" ] || { echo "러너 $VER 의 SHA-256 을 릴리스 노트에서 찾지 못했습니다"; exit 1; }

mkdir -p "$DIR" && cd "$DIR"
curl -fsSL -o "$PKG" "https://github.com/actions/runner/releases/download/v$VER/$PKG"
echo "$SHA  $PKG" | shasum -a 256 -c -
tar xzf "$PKG"

./config.sh --unattended --url "https://github.com/$REPO" --name "$NAME" --labels macOS \
  --token "$(gh api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token)"
./svc.sh install
./svc.sh start
gh variable set SELF_HOSTED_MACOS --repo "$REPO" --body 1
echo "✅ 등록했습니다: $NAME (labels: self-hosted, macOS). 확인: gh api repos/$REPO/actions/runners --jq '.runners[].name'"
