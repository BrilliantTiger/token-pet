#!/bin/zsh
# 릴리스 워크플로의 mac 잡이 마지막에 부른다:  zsh ci/release_mac_gate.zsh <본문을 쓸 파일>
#
# release.sh 의 게시 전 검사를 **그대로** 돌린다 — 올릴 네 파일의 이름이 업데이터의 표와 맞는지, 그리고
# 파일 하나하나를 열어 펫 자산·코드 동일성·버전·아키텍처·서명·공증·티켓을 본다(verify_upload_artifact).
# 이어서 릴리스 본문을 만든다(gen_release_notes: 설치 안내 + 이 버전의 절).
#
# 검사를 여기 다시 적지 않으려고 release.sh 를 source 한다. 그 파일의 source 가드가 맨 아래 dispatch 앞에서
# 돌아오므로 함수만 생기고 아무 단계도 돌지 않는다(tests/test_source_guard.py). `./release.sh publish` 를
# 부르지 않는 까닭: 그것은 검사 뒤에 곧바로 공개 릴리스를 만든다 — Windows 파일이 붙기 전에.
# 게시는 publish 잡이 초안으로 올려 확인한 뒤에 한다.
set -e
cd "$(dirname "$0")/.."
[ -n "$1" ] || { echo "사용법: zsh ci/release_mac_gate.zsh <본문 파일>"; exit 1; }
out="$1"
source ./release.sh
typeset -f verify_upload_artifact gen_release_notes >/dev/null \
  || { echo "❌ release.sh 에서 검사 함수를 얻지 못했습니다"; exit 1; }

files=("$ZIP" "$UZIP" "$DMG" "$UDMG")
"$PY" verify_release_artifact.py assets "${files[@]}" \
  || { echo "❌ 업로드 목록이 업데이터의 자산 표와 맞지 않습니다"; exit 1; }
for f in "${files[@]}"; do
  verify_upload_artifact "$f" || { echo "❌ 게시 전 검사 실패: $f"; exit 1; }
  echo "✅ 게시 전 검사 통과: $f"
done

gen_release_notes "$out"
grep -q "^\*\*v$(cur_version)\*\*" "$out" \
  || { echo "❌ 릴리스 본문에 v$(cur_version) 절이 없습니다"; exit 1; }
echo "✅ 릴리스 본문: $(wc -l < "$out" | tr -d ' ') 줄"
