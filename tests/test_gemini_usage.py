"""Gemini(Antigravity CLI, `agy`) 사용량 게이팅 테스트 — TOK-44, Verifier 작성, 구현 전.

이 파일은 아직 없는 동작을 고정한다. 작성 시점에 전부 빨강이어야 하고(AGENTS.md §3), 빨강은
ImportError 가 아니라 `_require` 의 AssertionError 로 나야 한다 — 그래야 '무엇이 없는지'가
실패 메시지에 남는다(tests/test_summary_layout.py::_require 와 같은 방식).

── 계약 (Coordinator 결정, claude_pet.py 의 모듈 함수) ─────────────────────────────────

1. `parse_antigravity_credential(secret) -> dict | None` — 키체인 비밀값 문자열을 읽는다.
   `go-keyring-base64:` 형식과 평문 JSON 형식을 받는다. `{"access_token": str, "expiry":
   aware datetime | None}`(키가 더 있어도 된다) 또는, 망가졌거나 비었거나 access_token 이
   없으면 None. 절대 예외를 내지 않는다.
2. `parse_gemini_quota(quota, summary=None) -> list[tuple] | None` — 순수 함수. 행 모양은
   Codex 와 같은 `(label, pct, reset_dt, reset_text)`; pct 는 **쓴** 비율(0–100, float),
   reset_dt 는 aware UTC datetime 또는 None, reset_text 는 None.
     · 0행 `"gemini"`: modelId 가 `"gemini-"` 로 시작하고 쓸 수 있는 remainingFraction
       (숫자 또는 숫자 문자열, [0,1] 로 자름)을 가진 버킷 중 **남은 비율이 가장 낮은** 것.
       pct = (1 − 그 값) × 100, reset = 그 버킷의 resetTime(최저값이 여럿이면 가장 이른 것).
       remainingFraction 이 없거나 null 이거나 숫자가 아니면 건너뛴다 — 100% 도 0% 도 아니다.
       Gemini 가 아닌 버킷은 이 행에 영향을 주지 않는다.
     · 이어서 Gemini 모델 버킷마다 한 행, `"gemini:<modelId>"`, modelId 순.
     · 이어서 summary 가 있으면 summary 버킷마다 한 행, `"gemini_group:<bucketId>"`, 서버 순서.
     · 쓸 수 있는 Gemini 버킷도 summary 버킷도 없으면 None(0% 블록을 지어내지 않는다).
3. `fetch_gemini_usage() -> list | None` — macOS 에서만 `security find-generic-password
   -s gemini -a antigravity -w` 로 자격증명을 읽고, loadCodeAssist → retrieveUserQuota
   (+ retrieveUserQuotaSummary — 이쪽 실패가 quota 행을 잃게 하면 안 된다)를
   `User-Agent: antigravity/…` 와 Bearer 토큰으로 부른 뒤 `parse_gemini_quota(...)` 를 준다.
   HTTP·네트워크 오류, 깨진 JSON, 자격증명 없음 → None, 그리고 호출자가 읽을 상태를 남긴다.
   토큰은 어떤 로그·디버그 출력·예외 문구에도 나오지 않는다. 이미 만료된(또는 요청 도중에
   만료될) 자격증명은 보내지 않는다 — None, 그리고 "expired" 상태(2026-11-18 Coordinator 추가:
   agy 를 닫아 두면 만료된 토큰이 키체인에 그대로 남는다).

── 이 파일이 Developer 에게 거는 이름 (Verifier 제안, 계약 3 의 "상태" 부분) ─────────────

  · `GEMINI_STATUS = {"auth_error": bool, "last_error": str | None}` — CODEX_STATUS 와 같은
    모양·같은 어휘(`http:<code>`, `net`, `parse`; 성공 뒤 None). `is_transient_fetch_error()`
    가 이 어휘를 그대로 읽으므로 새 어휘를 만들 이유가 없다. 하나만 더한다: 보내지 않은 만료
    토큰은 `last_error = "expired"`(일시 실패가 아니다). 그때 auth_error 는 이 파일이 정하지 않는다.
  · 캐시가 있다면 이름에 `gemini` 와 `cache` 를 함께 넣는다(제안: `_gemini_cache = {"t": 0.0,
    "rows": None, "ok_t": None}`). 이 파일의 하네스는 그런 이름의 **모듈 수준 dict** 를 매 호출
    전에 임포트 시점의 모양으로 되돌린다 — 180초 캐시가 앞 테스트의 행을 다음 테스트에 넘기지
    않게 하려는 것이고, 내부 구현을 단언하지는 않는다.
  · HTTP 는 `urllib.request.urlopen` 으로, 키체인은 `subprocess.run` 으로 나간다(Codex·Claude
    경로와 같다). 다른 길로 나가면 하네스가 소켓·프로세스를 막아 행이 없어지고 테스트가 빨개진다.
  · 플랫폼은 호출 시점에 `sys.platform` 으로 본다(keychain_locked 등 기존 관례) — 모듈 상수로
    굳히면 하네스의 플랫폼 패치가 닿지 않는다.

── 무엇이 관측이고 무엇이 계약인가 (AGENTS.md §5) ─────────────────────────────────────

관측(표본: Coordinator 가 2026-11-18 에 이 저장소 주인의 Mac 한 대에서, agy 1.5.10, Google AI
Ultra 계정 하나로 잰 것):
  · 키체인 항목 service `gemini` / account `antigravity`, 값은 `go-keyring-base64:` + base64(JSON),
    JSON 은 `{"token": {access_token, token_type, refresh_token, expiry, expires_in},
    "auth_method", "id_token_email"}`; expiry 예 `"2026-11-18T13:06:16.842436+09:00"`.
  · 같은 토큰으로 retrieveUserQuota 를 부르면 User-Agent 없이는 403, `antigravity/1.5.10
    darwin/arm64` 로는 200.
  · 응답 모양: quota.buckets[] = {modelId, tokenType:"WTUS", remainingFraction, resetTime?} —
    claude-*, gpt-oss-*, chat_*, tab_* 같은 비-Gemini 버킷이 섞여 있고 resetTime 이 없는
    버킷도 있다. summary.groups[] = {displayName, description, buckets[{bucketId, displayName,
    window, resetTime, remainingFraction}]}. 관측된 응답의 모든 비율은 1(새 계정)이었다.

명세에서 온 것(관측 아님):
  · `go-keyring-base64:` 는 zalando/go-keyring 의 macOS 인코딩이다(base64.StdEncoding).
  · token 객체는 golang.org/x/oauth2 의 Token JSON 이고, expiry 는 Go `time.Time` 의
    MarshalJSON — RFC 3339, 소수 초는 끝의 0 을 지워 0–9 자리, UTC 면 `Z`. 그래서 아래
    expiry 표는 관측된 6자리 `+09:00` 하나가 아니라 그 형식이 낼 수 있는 모양을 고루 담는다.
  · resetTime 은 proto3 JSON 의 Timestamp 모양(`Z` 정규화, 소수 초 0/3/6/9 자리)으로 보이고,
    그 가정 아래 3자리·9자리 소수 초를 하나씩 넣었다. 이것은 추론이다 — 틀렸다면 그 두 값을
    `Z` 정수 초로 바꾸면 되고, 나머지 단언은 그대로다.

픽스처는 전부 합성이다. 토큰·이메일·프로젝트 id 는 지어낸 값이고, 실측 응답에서 가져온 것은
**모양**(키 이름, modelId 목록, tokenType)뿐이다. 실측 파일은 읽지 않는다(CLAUDE.md "Testing
policy: synthetic fixtures only"). 테스트는 진짜 키체인·네트워크·`~/.gemini`·`~/.claude` 에
닿지 않는다: subprocess.run/Popen·os.system·ctypes.CDLL·urlopen·socket 을 막고 HOME 을 임시
디렉터리로 돌린다.
"""

import base64
import contextlib
import io
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import time as _time_module
import types
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()


UTC = timezone.utc
_MISSING = object()
_real_time = _time_module.time


def _require(name):
    value = getattr(claude_pet, name, None)
    if value is None:
        raise AssertionError(
            f"claude_pet.{name} 가 없다 — TOK-44 Gemini(agy) 사용량 계약이 아직 구현되지 "
            "않았다. 이 파일은 구현 전에 쓰였고 지금 빨간 것이 정상이다.")
    return value


def _utc(y, mo, d, h=0, mi=0, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=UTC)


# ═════════════════════════════ 합성 자격증명 ═════════════════════════════

TOKEN = "ya29.SYNTHETIC-ACCESS-TOKEN-7f3a9c"          # 지어낸 값
REFRESH = "1//SYNTHETIC-REFRESH-TOKEN-91c2d4"         # 지어낸 값
EMAIL = "synthetic.user@example.invalid"              # 지어낸 값 (예약 TLD)
PROJECT = "synthetic-project-0001"                    # 지어낸 값

OBSERVED_EXPIRY_TEXT = "2026-11-18T13:06:16.842436+09:00"     # 관측된 모양
OBSERVED_EXPIRY_INSTANT = _utc(2026, 11, 18, 4, 6, 16, 842436)  # 같은 순간, UTC


def credential_obj(token=TOKEN, expiry=OBSERVED_EXPIRY_TEXT):
    """키체인 JSON 의 관측된 모양. expiry=_MISSING 이면 키 자체를 뺀다."""
    tok = {"access_token": token, "token_type": "Bearer", "refresh_token": REFRESH,
           "expires_in": 3599}
    if expiry is not _MISSING:
        tok["expiry"] = expiry
    return {"token": tok, "auth_method": "consumer", "id_token_email": EMAIL}


def agy_secret(obj, form="b64"):
    """키체인에 들어 있는 문자열. form="b64" 는 go-keyring 형식, "json" 은 평문 JSON."""
    raw = obj if isinstance(obj, str) else json.dumps(obj)
    if form == "json":
        return raw
    return "go-keyring-base64:" + base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _expiry_text(instant, offset_hours):
    """aware 순간을 주어진 UTC 오프셋의 RFC 3339 문자열로 — Go 가 로컬 시간대로 쓰는 모양."""
    return instant.astimezone(timezone(timedelta(hours=offset_hours))).isoformat()


# ═════════════════════════════ 합성 quota / summary ═════════════════════════════
#
# 모양은 2026-11-18 관측 응답에서, 값은 전부 지어냈다. 서버 순서를 일부러 섞었다:
# 최저 Gemini 버킷(gemini-3-flash)은 **목록 가운데**에 있고, 그 resetTime 은 Gemini 버킷들 중
# 가장 이르지도 가장 늦지도 않다. 비-Gemini 버킷은 전부 그보다 낮은 비율이다.

R_CLAUDE = "2026-11-18T06:00:00Z"      # 전체에서 가장 이른 리셋 — 비-Gemini
R_PRO = "2026-11-18T07:00:00Z"         # Gemini 중 가장 이른 리셋 — 최저 버킷이 아니다
R_HEADLINE = "2026-11-18T08:45:41Z"    # 최저 Gemini 버킷(gemini-3-flash)의 리셋
R_FLASH = "2026-11-18T09:30:00.250Z"   # 3자리 소수 초
R_LITE = "2026-11-18T10:00:00.123456789Z"  # 9자리 소수 초 — Gemini 중 가장 늦은 리셋


def _b(model, frac=_MISSING, reset=_MISSING):
    b = {"tokenType": "WTUS", "modelId": model}
    if frac is not _MISSING:
        b["remainingFraction"] = frac
    if reset is not _MISSING:
        b["resetTime"] = reset
    return b


MAIN_QUOTA = {"buckets": [
    _b("chat_20706", 0.05),                                  # 비-Gemini, 리셋 없음
    _b("claude-opus-5-5-high", 0.10, R_CLAUDE),              # 비-Gemini
    _b("gemini-2.5-pro", 0.70, R_PRO),                       # 첫 Gemini, 최고 비율
    _b("gemini-2.5-flash-lite", None, R_HEADLINE),           # null → 건너뜀
    _b("gemini-3-flash", 0.25, R_HEADLINE),                  # ★ 최저 Gemini — 가운데
    _b("gemini-2.5-flash-thinking", "abc", R_HEADLINE),      # 숫자 아님 → 건너뜀
    _b("gemini-2.5-flash", 0.40, R_FLASH),
    _b("gemini-3.1-flash-lite", _MISSING, R_HEADLINE),       # 키 없음 → 건너뜀
    _b("gpt-oss-120b-medium", 0, R_HEADLINE),                # 비-Gemini, 0 (다 씀)
    _b("tab_gemini-2.5-flash-lite", 0.02),                   # 'gemini-' 를 품지만 접두사 아님
    _b("gemini-3.1-flash-image", True, R_HEADLINE),          # JSON true 는 숫자가 아니다
    _b("gemini-3.8-flash-tiered", "NaN", R_HEADLINE),        # 숫자 문자열이지만 유한하지 않다
    _b("gemini-3.5-flash-lite", "0.6", R_LITE),              # 숫자 문자열 → 받는다, 마지막 Gemini
    _b("tab_flash_lite_preview", 0.01),                      # 비-Gemini, 리셋 없음
]}

HEADLINE_ROW = ("gemini", 75.0, _utc(2026, 11, 18, 8, 45, 41), None)
MODEL_ROWS = [
    ("gemini:gemini-2.5-flash", 60.0, _utc(2026, 11, 18, 9, 30, 0, 250000), None),
    ("gemini:gemini-2.5-pro", 30.0, _utc(2026, 11, 18, 7, 0, 0), None),
    ("gemini:gemini-3-flash", 75.0, _utc(2026, 11, 18, 8, 45, 41), None),
    ("gemini:gemini-3.5-flash-lite", 40.0, _utc(2026, 11, 18, 10, 0, 0, 123456), None),
]

MAIN_SUMMARY = {
    "groups": [
        {"displayName": "Claude and GPT models",
         "description": "synthetic",
         "buckets": [
             # 서버 순서는 weekly 가 먼저다(관측 응답도 그랬다) — bucketId 정렬과 반대.
             {"bucketId": "3p-weekly", "displayName": "Weekly Limit Remaining",
              "window": "weekly", "resetTime": "2026-11-25T03:45:42Z",
              "remainingFraction": 0.9},
             # 0.10 은 최저 Gemini(0.25)보다 낮다 — summary 를 0행에 섞는 경쟁 구현을 가른다.
             {"bucketId": "3p-5h", "displayName": "Five Hour Limit Remaining",
              "window": "5h", "resetTime": "2026-11-18T08:45:42Z",
              "remainingFraction": 0.1},
         ]},
        # 두 번째 그룹은 지어냈다(관측된 계정에는 하나뿐이었다). groups[0] 만 읽는 구현을 가른다.
        {"displayName": "Synthetic second group",
         "description": "synthetic",
         "buckets": [
             {"bucketId": "x-broken", "displayName": "no fraction",
              "window": "5h", "resetTime": "2026-11-18T09:00:00Z"},
             {"bucketId": "x-weekly", "displayName": "string fraction",
              "window": "weekly", "resetTime": "2026-11-24T00:00:00Z",
              "remainingFraction": "0.5"},
         ]},
    ],
    "description": "synthetic",
}

GROUP_ROWS = [
    ("gemini_group:3p-weekly", 10.0, _utc(2026, 11, 25, 3, 45, 42), None),
    ("gemini_group:3p-5h", 90.0, _utc(2026, 11, 18, 8, 45, 42), None),
    ("gemini_group:x-weekly", 50.0, _utc(2026, 11, 24), None),
]

# 관측된 새 계정의 모양: Gemini 모델 아홉 개, 비율은 전부 정수 1, 리셋은 전부 같다.
OBSERVED_GEMINI_MODELS = (
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-thinking",
    "gemini-2.5-pro", "gemini-3-flash", "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash-tiered",
)
FRESH_RESET = "2026-11-18T08:45:41Z"
FRESH_QUOTA = {"buckets": (
    [_b("chat_20706", 1), _b("chat_23310", 1)]
    + [_b(m, 1, FRESH_RESET) for m in ("claude-opus-5-5-high", "claude-sonnet-5-5-low")]
    + [_b(m, 1, FRESH_RESET) for m in OBSERVED_GEMINI_MODELS]
    + [_b("gpt-oss-120b-medium", 1, FRESH_RESET), _b("tab_flash_lite_preview", 1)]
)}
FRESH_SUMMARY = {"groups": [{"displayName": "Claude and GPT models", "buckets": [
    {"bucketId": "3p-weekly", "window": "weekly", "resetTime": "2026-11-25T03:45:42Z",
     "remainingFraction": 1},
    {"bucketId": "3p-5h", "window": "5h", "resetTime": "2026-11-18T08:45:42Z",
     "remainingFraction": 1},
]}]}


def _assert_rows(test, got, expected, msg=""):
    """행 목록을 비교한다. 라벨·순서는 정확히, pct 는 1e-6 안에서, reset 은 aware UTC 이고
    1ms 안에서(소수 초를 자르든 반올림하든 같은 값으로 본다), reset_text 는 None."""
    test.assertIsInstance(got, list, "%s행은 list 여야 한다 (받은 것: %r)" % (msg, got))
    test.assertEqual([r[0] for r in got], [e[0] for e in expected],
                     "%s라벨·순서가 다르다" % msg)
    for row, exp in zip(got, expected):
        test.assertIsInstance(row, tuple, "%s%s: 행은 tuple 이어야 한다" % (msg, exp[0]))
        test.assertEqual(len(row), 4, "%s%s: 행은 (label, pct, reset_dt, reset_text)" % (msg, exp[0]))
        label, pct, reset, text = row
        test.assertIsInstance(pct, float, "%s%s: pct 는 float (받은 것 %r)" % (msg, label, pct))
        test.assertTrue(math.isfinite(pct), "%s%s: pct 가 유한하지 않다: %r" % (msg, label, pct))
        test.assertAlmostEqual(pct, exp[1], places=6,
                               msg="%s%s: pct %r != %r" % (msg, label, pct, exp[1]))
        if exp[2] is None:
            test.assertIsNone(reset, "%s%s: 리셋이 없어야 한다" % (msg, label))
        else:
            test.assertIsInstance(reset, datetime, "%s%s: reset 은 datetime" % (msg, label))
            test.assertIsNotNone(reset.tzinfo, "%s%s: reset 은 aware 여야 한다" % (msg, label))
            test.assertEqual(reset.utcoffset(), timedelta(0), "%s%s: reset 은 UTC" % (msg, label))
            test.assertLess(abs(reset - exp[2]), timedelta(milliseconds=1),
                            "%s%s: reset %r != %r" % (msg, label, reset, exp[2]))
        test.assertIsNone(text, "%s%s: reset_text 는 None (받은 것 %r)" % (msg, label, text))


# ═════════════════════════════ 1. 자격증명 ═════════════════════════════


class AntigravityCredentialTests(unittest.TestCase):
    """`parse_antigravity_credential(secret)` — 키체인 문자열 → {access_token, expiry}."""

    def _parse(self, secret):
        return _require("parse_antigravity_credential")(secret)

    def test_the_observed_keyring_form_yields_the_token_and_an_aware_expiry(self):
        """관측된 모양 그대로. expiry 는 **그 순간**이어야 한다(04:06:16.842436Z).
        Rivals: 오프셋을 버리고 naive 로 읽기(13:06 naive — aware 와 같지 않다); naive 로 읽고
        UTC 를 붙이기(13:06Z, 9시간 늦음); base64 를 안 풀고 JSON 으로 바로 읽기(None);
        최상위 access_token 을 찾기(None); refresh_token 을 토큰으로 쓰기."""
        cred = self._parse(agy_secret(credential_obj()))
        self.assertIsInstance(cred, dict, "관측된 형식을 읽지 못했다")
        self.assertEqual(cred.get("access_token"), TOKEN)
        exp = cred.get("expiry")
        self.assertIsInstance(exp, datetime)
        self.assertIsNotNone(exp.tzinfo, "expiry 가 naive 다 — 오프셋(+09:00)을 버렸다")
        self.assertEqual(exp, OBSERVED_EXPIRY_INSTANT,
                         "expiry 가 다른 순간이다 (받은 것 %r)" % (exp,))

    def test_the_plain_json_form_is_read_the_same_way(self):
        """접두사 없는 평문 JSON 도 같은 결과. Rival: go-keyring 형식만 받는 구현(None)."""
        cred = self._parse(agy_secret(credential_obj(), form="json"))
        self.assertIsInstance(cred, dict, "평문 JSON 형식을 읽지 못했다")
        self.assertEqual(cred.get("access_token"), TOKEN)
        self.assertEqual(cred.get("expiry"), OBSERVED_EXPIRY_INSTANT)

    def test_go_rfc3339_expiry_forms_all_parse_to_the_same_instant(self):
        """Go 의 time.Time JSON 은 소수 초 0–9 자리, UTC 면 `Z` 를 쓴다(모듈 독스트링).
        Rivals: `strptime(..., "%Y-%m-%dT%H:%M:%S.%f%z")`(소수 초 없음·9자리에서 실패);
        `Z` 를 못 읽는 파서; 소수 초를 6자리로 가정하는 정규식."""
        instant = _utc(2026, 11, 18, 4, 6, 16)
        cases = (
            ("observed 6 digits +09:00", "2026-11-18T13:06:16.842436+09:00",
             instant.replace(microsecond=842436)),
            ("no fraction -08:00", "2026-11-17T20:06:16-08:00", instant),
            ("Z, 9 digits", "2026-11-18T04:06:16.842436123Z", instant.replace(microsecond=842436)),
            ("Z, no fraction", "2026-11-18T04:06:16Z", instant),
            ("3 digits +05:30", "2026-11-18T09:36:16.5+05:30", instant.replace(microsecond=500000)),
        )
        for name, text, expected in cases:
            with self.subTest(form=name):
                cred = self._parse(agy_secret(credential_obj(expiry=text)))
                self.assertIsInstance(cred, dict)
                exp = cred.get("expiry")
                self.assertIsInstance(exp, datetime, "expiry 를 못 읽었다: %r" % text)
                self.assertIsNotNone(exp.tzinfo, "naive expiry: %r" % text)
                self.assertLess(abs(exp - expected), timedelta(milliseconds=1),
                                "%r → %r, 기대 %r" % (text, exp, expected))

    def test_a_missing_expiry_keeps_the_token_with_no_expiry(self):
        """expiry 가 없으면 expiry=None 이지 자격증명 전체가 None 이 아니다(계약 1의 타입).
        Rival: expiry 를 필수로 보는 구현(None)."""
        cred = self._parse(agy_secret(credential_obj(expiry=_MISSING)))
        self.assertIsInstance(cred, dict, "expiry 가 없다고 토큰까지 버렸다")
        self.assertEqual(cred.get("access_token"), TOKEN)
        self.assertIsNone(cred.get("expiry"))

    def test_malformed_secrets_are_none_never_an_exception(self):
        """망가진 모든 입력은 None 이고 예외가 아니다.
        Rivals: base64·JSON 오류를 그대로 던지는 구현; `{"token": null}` 에서 AttributeError;
        빈 문자열 토큰·숫자 토큰을 토큰으로 받는 구현; 비-str 입력에서 TypeError."""
        good_inner = json.dumps(credential_obj())
        cases = (
            ("None", None),
            ("int", 42),
            ("list", ["x"]),
            ("empty", ""),
            ("blank", "   \n"),
            ("prefix only", "go-keyring-base64:"),
            ("bad base64", "go-keyring-base64:!!!not base64!!!"),
            ("base64 of non-json", agy_secret("not json at all")),
            ("base64 of truncated json", agy_secret(good_inner[:-7])),
            ("plain non-json", "definitely not json"),
            ("json list", agy_secret([credential_obj()])),
            ("token null", agy_secret({"token": None})),
            ("token string", agy_secret({"token": TOKEN})),
            ("empty object", agy_secret({})),
            ("token without access", agy_secret({"token": {"refresh_token": REFRESH}})),
            ("access empty", agy_secret(credential_obj(token=""))),
            ("access blank", agy_secret(credential_obj(token="   "))),
            ("access number", agy_secret(credential_obj(token=12345))),
            ("access null", agy_secret(credential_obj(token=None))),
        )
        for name, secret in cases:
            with self.subTest(case=name):
                try:
                    got = self._parse(secret)
                except Exception as e:  # noqa: BLE001 — 예외 자체가 실패다
                    self.fail("예외를 냈다: %s" % type(e).__name__)
                self.assertIsNone(got, "망가진 입력에서 자격증명이 나왔다: %r" % (got,))

    def test_reading_logs_no_secret(self):
        """읽기 경로의 _dbg·stdout·stderr 에 토큰·refresh 토큰·이메일이 없다 — 성공과 실패 둘 다.
        Rival: `_dbg("agy cred", obj)`; 깨진 JSON 의 원문을 로그에 싣는 구현."""
        fn = _require("parse_antigravity_credential")
        good_inner = json.dumps(credential_obj())
        for name, secret in (("ok", agy_secret(credential_obj())),
                             ("truncated", agy_secret(good_inner[:-7])),
                             ("plain truncated", good_inner[:-7])):
            with self.subTest(case=name):
                seen, out, err = [], io.StringIO(), io.StringIO()
                with mock.patch.object(claude_pet, "_dbg", lambda *a, **k: seen.append(a)), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        fn(secret)
                    except Exception as e:  # noqa: BLE001
                        self.fail("예외를 냈다: %s" % type(e).__name__)
                text = " ".join(str(x) for a in seen for x in a) + out.getvalue() + err.getvalue()
                for secret_part in (TOKEN, REFRESH, EMAIL):
                    self.assertNotIn(secret_part, text)


# ═════════════════════════════ 2. quota 파싱 ═════════════════════════════


class GeminiQuotaParseTests(unittest.TestCase):
    """`parse_gemini_quota(quota, summary=None)` — 순수 함수.

    MAIN_QUOTA 의 0행 진리표(AGENTS.md §3, scratch 로 계산해 확인):

    | 구현                                   | pct    | reset              |
    | ------------------------------------- | ------ | ------------------ |
    | **최저 Gemini (계약)**                  | **75** | **08:45:41Z**      |
    | 최고(max)                              | 30     | 07:00Z             |
    | 서버 순서 첫 Gemini                     | 30     | 07:00Z             |
    | 서버 순서 마지막 쓸 수 있는 Gemini        | 40     | 10:00:00.123Z      |
    | modelId 정렬 첫 행                      | 60     | 09:30:00.25Z       |
    | 평균                                   | 51.25  | —                  |
    | 비-Gemini 포함(전체 최저 gpt-oss 0)      | 100    | 08:45:41Z          |
    | claude-* 포함                          | 90     | 06:00Z             |
    | 'gemini-' 포함(접두사 아님) — tab_gemini  | 98     | None               |
    | 없음/null/'abc' 를 0 으로               | 100    | 08:45:41Z          |
    | 남은 비율을 그대로(쓴 비율 아님)           | 25     | 08:45:41Z          |
    | ×100 누락                              | 0.75   | 08:45:41Z          |
    | summary 를 0행에 섞음(3p-5h 0.10)        | 90     | 08:45:42Z          |
    | 리셋 = Gemini 중 가장 이른 것             | 75     | 07:00Z             |
    | 리셋 = 전체에서 가장 이른 것              | 75     | 06:00Z             |

    0행이 계약과 같아지는 경쟁 구현(없음을 1.0 으로, 숫자 문자열 거부, bool 을 숫자로, "NaN" 을
    float 으로)은 **모델 행 목록**이 갈라 놓는다 — 각각 행이 하나 늘거나 줄거나 nan 이 된다.
    """

    def _parse(self, quota, summary=None):
        fn = _require("parse_gemini_quota")
        if summary is None:
            return fn(quota)
        return fn(quota, summary)

    def test_the_headline_is_the_lowest_gemini_fraction_and_its_reset(self):
        """0행만 본다 — 위 진리표의 모든 경쟁 구현이 여기서 다른 값을 낸다."""
        rows = self._parse(MAIN_QUOTA, MAIN_SUMMARY)
        self.assertIsInstance(rows, list)
        self.assertTrue(rows, "행이 없다")
        _assert_rows(self, rows[:1], [HEADLINE_ROW], "0행: ")

    def test_rows_are_headline_then_models_by_id_then_groups_in_server_order(self):
        """전체 목록. 모델 행은 modelId 정렬(서버 순서 2.5-pro, 3-flash, 2.5-flash, 3.5-flash-lite
        와 다르다), 그룹 행은 서버 순서(3p-weekly 먼저 — bucketId 정렬과 반대), 두 그룹 모두.
        Rivals: 모델 행을 서버 순서·pct 순으로; 그룹 행을 bucketId 정렬로; groups[0] 만;
        displayName 을 라벨로; 없음을 1.0 으로(gemini-3.1-flash-lite 0% 행이 생김); 숫자 문자열
        거부(3.5-flash-lite·x-weekly 행이 빠짐); True 를 1 로(3.1-flash-image 0% 행);
        "NaN" 을 받음(3.8-flash-tiered nan 행); 0행 리셋을 모든 행에 붙임;
        fmt_countdown 문자열을 reset_text 에(계약은 None)."""
        rows = self._parse(MAIN_QUOTA, MAIN_SUMMARY)
        _assert_rows(self, rows, [HEADLINE_ROW] + MODEL_ROWS + GROUP_ROWS)

    def test_without_a_summary_there_are_no_group_rows(self):
        """summary 를 안 주면 0행 + 모델 행만. Rival: summary=None 에서 예외; 빈 그룹 행."""
        rows = self._parse(MAIN_QUOTA)
        _assert_rows(self, rows, [HEADLINE_ROW] + MODEL_ROWS)

    def test_a_lowest_fraction_tie_takes_the_earliest_reset(self):
        """최저값 동률은 가장 이른 resetTime. 동률 셋 중 가장 이른 것을 **가운데**에 뒀다(§3:
        둘이면 첫째나 마지막과 반드시 겹친다). 동률이 아닌 버킷이 그보다 더 이르다.

        | 구현                    | reset  |
        | ---------------------- | ------ |
        | **동률 중 가장 이른 것**  | **09:00** |
        | 동률 첫째(first-wins)    | 11:00  |
        | 동률 마지막(last-wins)   | 10:00  |
        | 동률 중 가장 늦은 것      | 11:00  |
        | 비율 무시, 가장 이른 것   | 08:00  |
        """
        quota = {"buckets": [
            _b("gemini-x", 0.2, "2026-11-18T11:00:00Z"),
            _b("gemini-w", 0.5, "2026-11-18T08:00:00Z"),
            _b("gemini-y", 0.2, "2026-11-18T09:00:00Z"),
            _b("gemini-z", 0.2, "2026-11-18T10:00:00Z"),
        ]}
        rows = self._parse(quota)
        self.assertIsInstance(rows, list)
        _assert_rows(self, rows[:1], [("gemini", 80.0, _utc(2026, 11, 18, 9), None)], "동률: ")

    def test_fractions_are_clamped_to_zero_one(self):
        """[0,1] 밖의 비율은 자른다. Rival: 자르지 않음(0행 125%, gemini-a −50%)."""
        quota = {"buckets": [
            _b("gemini-a", 1.5, "2026-11-18T08:00:00Z"),
            _b("gemini-b", -0.25, "2026-11-18T09:00:00Z"),
        ]}
        rows = self._parse(quota)
        _assert_rows(self, rows, [
            ("gemini", 100.0, _utc(2026, 11, 18, 9), None),
            ("gemini:gemini-a", 0.0, _utc(2026, 11, 18, 8), None),
            ("gemini:gemini-b", 100.0, _utc(2026, 11, 18, 9), None),
        ])

    def test_unusable_fractions_are_skipped_not_zero_or_full(self):
        """나쁜 비율 하나만 다르게 한 표. 그 버킷은 행을 내지 않고 0행에도 영향이 없다.
        다른 Gemini 버킷(0.5)이 하나 있어 0행은 늘 50% 다.
        Rivals: 없음/null 을 1.0 으로(0% 행이 생김) 또는 0.0 으로(0행 100%); 숫자 아닌 문자열을
        0 으로; bool 을 숫자로; "NaN"/NaN 을 받음(nan 행 또는 nan 0행)."""
        bad_values = (("missing", _MISSING), ("null", None), ("text", "abc"),
                      ("empty text", ""), ("true", True), ("false", False),
                      ("nan text", "NaN"), ("nan float", float("nan")),
                      ("list", [0.1]), ("object", {"v": 0.1}))
        for name, value in bad_values:
            with self.subTest(value=name):
                quota = {"buckets": [
                    _b("gemini-bad", value, "2026-11-18T07:00:00Z"),
                    _b("gemini-good", 0.5, "2026-11-18T08:00:00Z"),
                ]}
                rows = self._parse(quota)
                _assert_rows(self, rows, [
                    ("gemini", 50.0, _utc(2026, 11, 18, 8), None),
                    ("gemini:gemini-good", 50.0, _utc(2026, 11, 18, 8), None),
                ])

    def test_a_bucket_without_a_usable_reset_keeps_its_row(self):
        """resetTime 이 없거나 못 읽어도 수치 행은 남는다(Codex 와 같은 규칙), reset=None.
        Rivals: 리셋 없는 버킷을 버림; 못 읽는 resetTime 에서 예외; 문자열을 그대로 reset 에."""
        quota = {"buckets": [
            _b("gemini-no-reset", 0.3),
            _b("gemini-bad-reset", 0.6, "soon"),
        ]}
        rows = self._parse(quota)
        _assert_rows(self, rows, [
            ("gemini", 70.0, None, None),
            ("gemini:gemini-bad-reset", 40.0, None, None),
            ("gemini:gemini-no-reset", 70.0, None, None),
        ])

    def test_no_usable_bucket_means_none_not_zero(self):
        """쓸 수 있는 Gemini 버킷도 summary 버킷도 없으면 None — 빈 목록도 0% 행도 아니다.
        Rivals: [] 반환; ("gemini", 0.0, …) 행을 지어냄; 비-Gemini 버킷으로 0행을 채움."""
        only_others = {"buckets": [_b("claude-opus-5-5-high", 0.3, R_CLAUDE),
                                   _b("chat_20706", 0.1),
                                   _b("gemini-2.5-pro", None, R_PRO)]}
        unusable_summary = {"groups": [{"buckets": [
            {"bucketId": "3p-5h", "window": "5h", "resetTime": R_HEADLINE}]}]}
        cases = (
            ("no buckets", {"buckets": []}, None),
            ("only non-gemini", only_others, None),
            ("only non-gemini + unusable summary", only_others, unusable_summary),
            ("empty summary", {"buckets": []}, {"groups": []}),
        )
        for name, quota, summary in cases:
            with self.subTest(case=name):
                self.assertIsNone(self._parse(quota, summary))

    def test_group_rows_alone_when_no_gemini_bucket(self):
        """Gemini 버킷이 없고 summary 만 쓸 수 있으면 그룹 행만 — '"gemini"' 0행을 지어내지 않는다
        (계약의 None 조건이 'AND' 라서 행 목록은 있어야 하고, 0행은 근거가 없다).
        Rivals: None 반환(그룹 값을 버림); 0% "gemini" 행을 앞에 붙임."""
        rows = self._parse({"buckets": [_b("claude-opus-5-5-high", 0.3, R_CLAUDE)]}, MAIN_SUMMARY)
        _assert_rows(self, rows, GROUP_ROWS)

    def test_the_observed_fresh_account_is_a_real_zero(self):
        """관측된 새 계정 모양(비율 전부 정수 1): 0행 0.0, Gemini 모델 아홉 행, 그룹 두 행.
        서버가 '남은 비율 1' 이라고 말했으니 이 0% 는 지어낸 것이 아니다. pct 는 float 다 —
        정수 비율에서 `(1 - 1) * 100` 은 int 0 이 된다.
        Rivals: int pct; 비-Gemini(claude·gpt-oss·chat·tab) 행을 모델 행에 넣음."""
        reset = _utc(2026, 11, 18, 8, 45, 41)
        expected = ([("gemini", 0.0, reset, None)]
                    + [("gemini:" + m, 0.0, reset, None) for m in sorted(OBSERVED_GEMINI_MODELS)]
                    + [("gemini_group:3p-weekly", 0.0, _utc(2026, 11, 25, 3, 45, 42), None),
                       ("gemini_group:3p-5h", 0.0, _utc(2026, 11, 18, 8, 45, 42), None)])
        _assert_rows(self, self._parse(FRESH_QUOTA, FRESH_SUMMARY), expected)

    def test_garbage_input_does_not_raise(self):
        """어떤 모양이 와도 예외 없이 None(또는, 쓸 수 있는 버킷이 남으면 그 행).
        Rival: `quota["buckets"]` 를 바로 순회해 TypeError/KeyError."""
        garbage = (None, [], "x", 42, {}, {"buckets": None}, {"buckets": "x"},
                   {"buckets": [None, 1, "x", [], {"modelId": 5, "remainingFraction": 0.5},
                                {"remainingFraction": 0.5}]})
        summaries = (None, [], "x", {"groups": None}, {"groups": "x"},
                     {"groups": [None, 1, {"buckets": None}, {"buckets": [None, {"bucketId": 3}]}]})
        fn = _require("parse_gemini_quota")
        for q in garbage:
            for s in summaries:
                with self.subTest(quota=repr(q)[:40], summary=repr(s)[:40]):
                    try:
                        got = fn(q, s)
                    except Exception as e:  # noqa: BLE001
                        self.fail("예외를 냈다: %s" % type(e).__name__)
                    self.assertIsNone(got)


# ═════════════════════════════ 3. 조회 하네스 ═════════════════════════════


def _gemini_dict_names(need_cache=True):
    out = []
    for name, value in vars(claude_pet).items():
        low = name.lower()
        if isinstance(value, dict) and "gemini" in low and (not need_cache or "cache" in low):
            out.append(name)
    return out


# 임포트 시점(어떤 테스트도 돌기 전)의 캐시 모양. 매 호출 전에 이것으로 되돌린다.
_PRISTINE_CACHES = {n: dict(getattr(claude_pet, n)) for n in _gemini_dict_names()}


def _restore_dict(d, snapshot):
    d.clear()
    d.update(snapshot)


def _arg_after(argv, flag):
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


class _Processes:
    """subprocess.run 의 대역 — 아무것도 실행하지 않는다.

    `security find-generic-password -s gemini -a antigravity -w` 에만 비밀값(+ 개행, 진짜
    security 처럼)으로 답하고, 그 밖의 `security` 호출과 다른 명령은 기록하고 rc 1/44 로 답한다.
    Popen·os.system·ctypes.CDLL 은 기록하고 거절한다 — 진짜 키체인에 닿을 다른 길을 막는다.
    """

    def __init__(self, secret):
        self.secret = secret
        self.security = []
        self.other = []
        self.blocked = []

    def run(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)):
            argv = str(argv).split()
        argv = [str(x) for x in argv]
        text = bool(k.get("text") or k.get("universal_newlines") or k.get("encoding")
                    or k.get("errors"))
        conv = (lambda s: s) if text else (lambda s: s.encode("utf-8"))
        if argv and os.path.basename(argv[0]) == "security":
            self.security.append(argv)
            wanted = ("find-generic-password" in argv and "-w" in argv
                      and _arg_after(argv, "-s") == "gemini"
                      and _arg_after(argv, "-a") == "antigravity")
            if wanted and self.secret is not None:
                res = subprocess.CompletedProcess(argv, 0, conv(self.secret + "\n"), conv(""))
            else:
                res = subprocess.CompletedProcess(
                    argv, 44, conv(""),
                    conv("security: SecKeychainSearchCopyNext: The specified item could not "
                         "be found in the keychain.\n"))
        else:
            self.other.append(argv[:1])
            res = subprocess.CompletedProcess(argv, 1, conv(""), conv(""))
        if k.get("check") and res.returncode:
            raise subprocess.CalledProcessError(res.returncode, argv, res.stdout, res.stderr)
        return res

    def popen(self, *a, **k):
        self.blocked.append(("Popen", repr(a[:1])[:80]))
        raise OSError("Popen 은 이 테스트에서 막혀 있다")

    def system(self, *a, **k):
        self.blocked.append(("os.system", repr(a[:1])[:80]))
        return 1

    def cdll(self, name, *a, **k):
        self.blocked.append(("CDLL", str(name)))
        raise OSError("ctypes.CDLL 은 이 테스트에서 막혀 있다")


class _Resp(io.BytesIO):
    status = 200
    code = 200
    headers = {}

    def getcode(self):
        return 200

    def info(self):
        return {}


ENDPOINTS = ("loadCodeAssist", "retrieveUserQuota", "retrieveUserQuotaSummary")
_HOSTS = ("cloudcode-pa.googleapis.com", "daily-cloudcode-pa.googleapis.com")


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "synthetic %d" % code, {},
                                  io.BytesIO(b'{"error": {"code": %d}}' % code))


class _FakeCloudCode:
    """cloudcode-pa 의 대역. 관측된 서버 행동을 흉내 낸다:
      · Bearer 토큰이 TOKEN 이 아니면 401;
      · retrieveUserQuota 는 User-Agent 가 `antigravity/` 로 시작하지 않으면 403(관측);
      · quota·summary 는 본문 `project` 가 PROJECT 문자열이 아니면 400.
    `fail` 은 엔드포인트 → HTTP 코드(int) | "net" | "garbage"."""

    def __init__(self, load=None, quota=None, summary=None, fail=None):
        self.bodies = {
            "loadCodeAssist": {"cloudaicompanionProject": PROJECT} if load is None else load,
            "retrieveUserQuota": MAIN_QUOTA if quota is None else quota,
            "retrieveUserQuotaSummary": MAIN_SUMMARY if summary is None else summary,
        }
        self.fail = dict(fail or {})
        self.requests = []

    def by(self, endpoint):
        return [r for r in self.requests if r.endpoint == endpoint]

    def __call__(self, req, data=None, timeout=None, *a, **kw):
        if isinstance(req, urllib.request.Request):
            url = req.full_url
            headers = {k.lower(): v for k, v in req.header_items()}
            raw = data if data is not None else req.data
            method = req.get_method() if data is None else (getattr(req, "method", None)
                                                            or "POST")
        else:
            url, headers, raw = str(req), {}, data
            method = "POST" if data is not None else "GET"
        try:
            body = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except Exception:  # noqa: BLE001
            body = _MISSING
        parts = urllib.parse.urlsplit(url)
        endpoint = parts.path.rsplit(":", 1)[-1] if ":" in parts.path else parts.path
        self.requests.append(types.SimpleNamespace(
            endpoint=endpoint, url=url, scheme=parts.scheme, host=parts.netloc,
            path=parts.path, method=method, headers=headers, body=body))
        if endpoint not in ENDPOINTS:
            raise _http_error(url, 404)
        f = self.fail.get(endpoint)
        if f == "net":
            raise urllib.error.URLError("synthetic network failure")
        if isinstance(f, int):
            raise _http_error(url, f)
        if headers.get("authorization") != "Bearer " + TOKEN:
            raise _http_error(url, 401)
        if (endpoint == "retrieveUserQuota"
                and not headers.get("user-agent", "").startswith("antigravity/")):
            raise _http_error(url, 403)
        if endpoint != "loadCodeAssist" and (not isinstance(body, dict)
                                             or body.get("project") != PROJECT):
            raise _http_error(url, 400)
        if f == "garbage":
            return _Resp(b"{not json")
        return _Resp(json.dumps(self.bodies[endpoint]).encode("utf-8"))


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:  # noqa: BLE001
            self.lines.append(repr(record.msg))


def _valid_expiry():
    return _expiry_text(datetime.now(UTC) + timedelta(hours=1), 9)


def _run_fetch(test, secret, server=None, platform="darwin", status_before=None,
               fresh_state=True, clock_shift=0.0):
    """fetch_gemini_usage() 를 한 번 돌린다. 진짜 키체인·네트워크·홈에 닿을 길은 전부 막는다.

    fresh_state=False 면 캐시를 임포트 시점으로 되돌리지 않는다(앞 호출의 행이 남아 있다).
    clock_shift 는 `time.time()` 을 그만큼(초) 뒤로 민다 — 캐시가 오래됐다는 것을 내부 이름에
    기대지 않고 '시간이 흘렀다'로 만든다. datetime.now() 는 진짜 시각 그대로다."""
    fn = _require("fetch_gemini_usage")
    server = _FakeCloudCode() if server is None else server
    procs = _Processes(secret)
    home = tempfile.mkdtemp(prefix="claudepet-gemini-")
    test.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))

    for name in _gemini_dict_names(need_cache=False):
        d = getattr(claude_pet, name)
        test.addCleanup(_restore_dict, d, dict(d))
    if fresh_state:
        for name, snap in _PRISTINE_CACHES.items():
            _restore_dict(getattr(claude_pet, name), snap)
    status = getattr(claude_pet, "GEMINI_STATUS", None)
    if isinstance(status, dict) and status_before is not None:
        status.update(status_before)

    dbg, out, err, logs = [], io.StringIO(), io.StringIO(), _ListHandler()
    root = logging.getLogger()
    old_level = root.level
    raised = None
    with contextlib.ExitStack() as st:
        env = dict(os.environ)
        env.update({"HOME": home, "USERPROFILE": home})
        env.pop("CLAUDE_PET_DEBUG", None)
        st.enter_context(mock.patch.dict(os.environ, env, clear=True))
        st.enter_context(mock.patch.object(sys, "platform", platform))
        if clock_shift:
            st.enter_context(mock.patch.object(claude_pet.time, "time",
                                               lambda: _real_time() + clock_shift))
        st.enter_context(mock.patch.object(claude_pet.subprocess, "run", procs.run))
        st.enter_context(mock.patch.object(claude_pet.subprocess, "Popen", procs.popen))
        st.enter_context(mock.patch.object(claude_pet.os, "system", procs.system))
        st.enter_context(mock.patch.object(claude_pet.ctypes, "CDLL", procs.cdll))
        st.enter_context(mock.patch.object(claude_pet, "keychain_locked", lambda: False,
                                           create=True))
        st.enter_context(mock.patch.object(claude_pet.urllib.request, "urlopen", server))
        st.enter_context(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: dbg.append(a)))
        st.enter_context(mock.patch("socket.create_connection",
                                    side_effect=AssertionError("테스트가 네트워크에 나가려 했다")))
        st.enter_context(contextlib.redirect_stdout(out))
        st.enter_context(contextlib.redirect_stderr(err))
        root.addHandler(logs)
        root.setLevel(logging.DEBUG)
        try:
            rows = fn()
        except Exception as e:  # noqa: BLE001 — 아래에서 실패로 보고한다
            rows, raised = None, e
        finally:
            root.removeHandler(logs)
            root.setLevel(old_level)
        status_after = dict(claude_pet.GEMINI_STATUS) if isinstance(
            getattr(claude_pet, "GEMINI_STATUS", None), dict) else None
    secret_text = " ".join(str(x) for a in dbg for x in a) + "\n" + out.getvalue() + "\n" \
        + err.getvalue() + "\n" + "\n".join(logs.lines)
    return types.SimpleNamespace(rows=rows, raised=raised, server=server, procs=procs,
                                 dbg=dbg, log_text=secret_text, status=status_after)


def _assert_no_raise(test, r):
    if r.raised is not None:
        test.fail("fetch_gemini_usage 가 예외를 냈다: %s (토큰이 문구에 %s)" % (
            type(r.raised).__name__,
            "있다" if TOKEN in str(r.raised) else "없다"))


def _secret(expiry=_MISSING):
    return agy_secret(credential_obj(expiry=_valid_expiry() if expiry is _MISSING else expiry))


# ═════════════════════════════ 3. 조회 ═════════════════════════════


class GeminiFetchTests(unittest.TestCase):
    """`fetch_gemini_usage()` — 키체인 → loadCodeAssist → retrieveUserQuota(+Summary)."""

    def test_the_credential_comes_from_the_agy_keychain_item_via_security(self):
        """`security find-generic-password -s gemini -a antigravity -w` 로 읽는다. 다른 길로는
        키체인에 가지 않는다(Popen·os.system·Security.framework 로드 없음).
        Rivals: service/account 를 뒤바꿈(-s antigravity -a gemini); -w 없이 속성 덤프를 파싱;
        `~/.gemini/oauth_creds.json`(Gemini CLI 의 파일 — agy 가 아니다)을 읽음;
        네이티브 Keychain API(프롬프트를 띄울 수 있는 경로)."""
        r = _run_fetch(self, _secret())
        _assert_no_raise(self, r)
        wanted = [a for a in r.procs.security
                  if "find-generic-password" in a and "-w" in a
                  and _arg_after(a, "-s") == "gemini" and _arg_after(a, "-a") == "antigravity"]
        self.assertTrue(wanted, "agy 키체인 항목을 security 로 읽지 않았다 (security 호출: %r)"
                        % (r.procs.security,))
        self.assertEqual([b for b in r.procs.blocked if b[0] != "CDLL" or "Security" in b[1]],
                         [], "키체인에 닿는 다른 길을 썼다")
        self.assertIsNotNone(r.rows, "자격증명을 읽고도 행이 없다")

    def test_the_three_calls_carry_bearer_user_agent_and_project(self):
        """요청 셋의 모양. loadCodeAssist 가 먼저고, quota·summary 는 그 뒤에 그 프로젝트로.
        Rivals: User-Agent 를 빠뜨림(관측: quota 403); 일부 호출에만 UA; GET; http://;
        다른 호스트; loadCodeAssist 를 건너뛰고 프로젝트 없이 quota; ideType 을 다른 값으로."""
        r = _run_fetch(self, _secret())
        _assert_no_raise(self, r)
        reqs = r.server.requests
        self.assertEqual(sorted({q.endpoint for q in reqs}), sorted(ENDPOINTS),
                         "세 엔드포인트를 정확히 불러야 한다 (부른 것: %r)"
                         % [q.endpoint for q in reqs])
        self.assertEqual(reqs[0].endpoint, "loadCodeAssist", "loadCodeAssist 가 먼저가 아니다")
        for q in reqs:
            with self.subTest(endpoint=q.endpoint):
                self.assertEqual(q.scheme, "https")
                self.assertIn(q.host, _HOSTS)
                self.assertEqual(q.path, "/v1internal:" + q.endpoint)
                self.assertEqual(q.method, "POST")
                self.assertEqual(q.headers.get("authorization"), "Bearer " + TOKEN)
                self.assertTrue(q.headers.get("user-agent", "").startswith("antigravity/"),
                                "User-Agent 가 antigravity/ 로 시작하지 않는다: %r"
                                % q.headers.get("user-agent"))
        load = r.server.by("loadCodeAssist")[0]
        self.assertIsInstance(load.body, dict, "loadCodeAssist 본문이 JSON 객체가 아니다")
        meta = load.body.get("metadata") or {}
        self.assertEqual(meta.get("ideType"), "ANTIGRAVITY")
        self.assertEqual(meta.get("pluginType"), "GEMINI")
        for ep in ("retrieveUserQuota", "retrieveUserQuotaSummary"):
            with self.subTest(body=ep):
                self.assertEqual(r.server.by(ep)[0].body, {"project": PROJECT})

    def test_the_rows_are_the_parsed_answer(self):
        """성공 경로의 행 = 0행 + 모델 행 + 그룹 행(값은 위 파서 테스트와 같은 독립 계산).
        상태는 성공으로 내려간다(앞서 auth_error 였어도). Rivals: summary 를 안 부름(그룹 행 없음);
        UA 없음(403 → None); 성공 뒤에도 auth_error 를 남김."""
        r = _run_fetch(self, _secret(),
                       status_before={"auth_error": True, "last_error": "http:401"})
        _assert_no_raise(self, r)
        _assert_rows(self, r.rows, [HEADLINE_ROW] + MODEL_ROWS + GROUP_ROWS)
        status = _require("GEMINI_STATUS")
        self.assertIsInstance(status, dict)
        self.assertEqual((r.status or {}).get("auth_error"), False)
        self.assertIsNone((r.status or {}).get("last_error"))

    def test_a_project_object_is_sent_as_its_id(self):
        """`cloudaicompanionProject` 가 `{"id": …}` 객체로 와도 quota 에는 id 문자열을 보낸다.
        Rival: 객체를 그대로 `project` 에 실음(가짜 서버 400 → None)."""
        server = _FakeCloudCode(load={"cloudaicompanionProject": {"id": PROJECT,
                                                                  "name": "synthetic"}})
        r = _run_fetch(self, _secret(), server=server)
        _assert_no_raise(self, r)
        quota_reqs = r.server.by("retrieveUserQuota")
        self.assertTrue(quota_reqs, "retrieveUserQuota 를 부르지 않았다")
        self.assertEqual(quota_reqs[0].body, {"project": PROJECT})
        _assert_rows(self, r.rows, [HEADLINE_ROW] + MODEL_ROWS + GROUP_ROWS)

    def test_a_failing_summary_keeps_the_quota_rows(self):
        """summary 가 어떻게 실패해도 quota 행(0행 + 모델 행)은 남는다.
        Rival: 세 호출을 한 try 에 묶어 summary 실패에서 None; summary 실패를 전체 실패로 기록해
        quota 행을 버림."""
        for name, fail, summary in (("500", 500, None), ("403", 403, None),
                                    ("404", 404, None), ("net", "net", None),
                                    ("garbage", "garbage", None),
                                    ("unusable body", None, {"groups": "x"})):
            with self.subTest(summary=name):
                server = _FakeCloudCode(
                    summary=summary,
                    fail={"retrieveUserQuotaSummary": fail} if fail is not None else None)
                r = _run_fetch(self, _secret(), server=server)
                _assert_no_raise(self, r)
                _assert_rows(self, r.rows, [HEADLINE_ROW] + MODEL_ROWS, "summary %s: " % name)

    def test_quota_failures_yield_none_and_record_a_status(self):
        """quota 가 실패하면 None, 그리고 GEMINI_STATUS 에 CODEX_STATUS 와 같은 어휘.
        401/403 만 auth_error. Rivals: 0% 행이나 summary 행만 돌려줌; 모든 실패를 auth_error 로;
        last_error 를 다른 어휘로(is_transient_fetch_error 가 못 읽음)."""
        cases = (
            ("401", {"retrieveUserQuota": 401}, True, "http:401"),
            ("403", {"retrieveUserQuota": 403}, True, "http:403"),
            ("500", {"retrieveUserQuota": 500}, False, "http:500"),
            ("429", {"retrieveUserQuota": 429}, False, "http:429"),
            ("net", {"retrieveUserQuota": "net"}, False, "net"),
            ("garbage", {"retrieveUserQuota": "garbage"}, False, "parse"),
        )
        for name, fail, auth, last in cases:
            with self.subTest(quota=name):
                r = _run_fetch(self, _secret(), server=_FakeCloudCode(fail=fail),
                               status_before={"auth_error": False, "last_error": None})
                _assert_no_raise(self, r)
                self.assertIsNone(r.rows, "quota 가 실패했는데 행이 있다: %r" % (r.rows,))
                _require("GEMINI_STATUS")
                self.assertEqual((r.status or {}).get("auth_error"), auth)
                self.assertEqual((r.status or {}).get("last_error"), last)

    def test_load_code_assist_failures_yield_none_and_record_a_status(self):
        """첫 호출(loadCodeAssist)이 실패해도 같은 규칙. 401 은 토큰 거부다.
        Rivals: 프로젝트 없이 quota 를 불러 400 을 기록; 첫 호출의 401 을 auth_error 로 안 올림."""
        for name, fail, auth, last in (("401", 401, True, "http:401"),
                                       ("503", 503, False, "http:503"),
                                       ("net", "net", False, "net"),
                                       ("garbage", "garbage", False, "parse")):
            with self.subTest(load=name):
                r = _run_fetch(self, _secret(),
                               server=_FakeCloudCode(fail={"loadCodeAssist": fail}),
                               status_before={"auth_error": False, "last_error": None})
                _assert_no_raise(self, r)
                self.assertIsNone(r.rows)
                _require("GEMINI_STATUS")
                self.assertEqual((r.status or {}).get("auth_error"), auth)
                self.assertEqual((r.status or {}).get("last_error"), last)

    def test_no_or_bad_credential_sends_nothing(self):
        """자격증명이 없거나 망가졌으면 요청이 하나도 없고 None. 자격증명 없음은 만료가 아니다 —
        앞서 올라가 있던 auth_error 도 내린다(CODEX_STATUS 와 같은 규칙).
        Rivals: 빈 토큰으로 요청; 망가진 비밀값에서 예외; 없음을 auth_error 로."""
        for name, secret in (("absent", None), ("garbage", "go-keyring-base64:!!!"),
                             ("no access token", agy_secret({"token": {"refresh_token": REFRESH}}))):
            with self.subTest(credential=name):
                r = _run_fetch(self, secret,
                               status_before={"auth_error": True, "last_error": "http:401"})
                _assert_no_raise(self, r)
                self.assertEqual(r.server.requests, [], "자격증명 없이 요청이 나갔다")
                self.assertIsNone(r.rows)
                _require("GEMINI_STATUS")
                self.assertEqual((r.status or {}).get("auth_error"), False)

    def test_an_expired_credential_is_not_sent(self):
        """expiry 가 지난 자격증명은 보내지 않는다 — 요청 0, None, 그리고
        `GEMINI_STATUS["last_error"] == "expired"`.

        관측(Coordinator, 2026-11-18, 실제 로그인 하나): agy 의 액세스 토큰은 한 시간마다 만료되고,
        agy 는 agy 프로세스가 떠 있을 때만 키체인 항목을 갱신한다. 그래서 agy 를 닫아 두면 만료된
        토큰이 키체인에 그대로 남는다 — 드문 경우가 아니라 평범한 상태다. 그때 필이 보여 줄 것은
        '자격증명 없음'(아무것도 안 보임)이 아니라 '만료'다. "expired" 는 is_transient_fetch_error()
        가 일시 실패로 보지 않는 어휘라, 직전 행을 붙들지 않는다(아래 다음 테스트).
        Rivals: expiry 를 보지 않고 보냄(가짜 서버는 토큰만 보므로 행이 생긴다); 보내지 않되 상태를
        남기지 않음(last_error None — 자격증명 없음과 구별되지 않는다); 다른 어휘(http:401 등)."""
        past = _expiry_text(datetime.now(UTC) - timedelta(hours=1), 0)
        r = _run_fetch(self, _secret(expiry=past),
                       status_before={"auth_error": False, "last_error": None})
        _assert_no_raise(self, r)
        self.assertEqual(r.server.requests, [], "만료된 토큰을 보냈다")
        self.assertIsNone(r.rows)
        _require("GEMINI_STATUS")
        self.assertEqual((r.status or {}).get("last_error"), "expired",
                         "만료를 상태로 남기지 않았다 (상태: %r)" % (r.status,))

    def test_after_expiry_the_last_good_rows_are_not_kept(self):
        """성공한 조회 뒤에 agy 가 닫혀 토큰이 만료되면, 캐시가 오래된 다음 조회는 None 이다 —
        직전 행을 붙들어 '만료' 대신 옛 숫자를 보여 주지 않는다(Codex 의 401 규칙과 같다).
        두 번째 호출은 캐시를 되돌리지 않고 `time.time()` 만 900초 민다.
        Rivals: 만료를 일시 실패처럼 다뤄 직전 행을 돌려줌; 만료된 토큰이면 캐시 행을 그대로 줌."""
        first = _run_fetch(self, _secret())
        _assert_no_raise(self, first)
        self.assertIsNotNone(first.rows, "첫 조회가 성공해야 이 테스트가 뜻이 있다")
        past = _expiry_text(datetime.now(UTC) - timedelta(minutes=5), 9)
        second = _run_fetch(self, _secret(expiry=past), fresh_state=False, clock_shift=900.0)
        _assert_no_raise(self, second)
        self.assertEqual(second.server.requests, [], "만료된 토큰을 보냈다")
        self.assertIsNone(second.rows, "만료 뒤에도 직전 행이 남았다: %r" % (second.rows,))
        _require("GEMINI_STATUS")
        self.assertEqual((second.status or {}).get("last_error"), "expired")

    def test_a_token_expiring_within_the_request_window_is_not_sent(self):
        """곧 만료될 토큰(3초 남음)은 이미 만료된 것으로 본다 — 요청 0, None, "expired".
        한 번의 조회는 요청 셋이고 각각 수 초가 걸릴 수 있어, 3초 남은 토큰은 도중에 죽는다.
        agy 자신(golang.org/x/oauth2)도 만료 10초 전부터 토큰을 무효로 본다(defaultExpiryDelta).
        반대쪽 경계: 10분 남은 토큰은 보낸다 — 토큰 수명이 한 시간(expires_in 3599)이라, 여백을
        그만큼 크게 잡는 구현은 시간의 상당 부분 동안 아무것도 못 읽는다.
        어느 여백이든 3초 초과 10분 미만이면 통과한다(정확한 값은 Developer 의 몫).
        Rivals: `expiry <= now` 만 봄(3초 남은 토큰을 보냄); 여백을 한 시간 단위로 잡음."""
        now = datetime.now(UTC)
        for name, delta, should_send in (("3 s left", timedelta(seconds=3), False),
                                         ("10 min left", timedelta(minutes=10), True)):
            with self.subTest(expiry=name):
                r = _run_fetch(self, _secret(expiry=_expiry_text(now + delta, 9)),
                               status_before={"auth_error": False, "last_error": None})
                _assert_no_raise(self, r)
                if should_send:
                    self.assertTrue(r.server.requests, "10분 남은 토큰을 보내지 않았다")
                    self.assertIsNotNone(r.rows)
                else:
                    self.assertEqual(r.server.requests, [], "곧 만료될 토큰을 보냈다")
                    self.assertIsNone(r.rows)
                    _require("GEMINI_STATUS")
                    self.assertEqual((r.status or {}).get("last_error"), "expired")

    def test_expiry_is_compared_as_an_instant_not_a_wall_clock(self):
        """오프셋을 품은 expiry 는 순간으로 비교한다. 두 경우가 짝이다:
          · +09:00 으로 적힌 '1시간 전' — 벽시계 숫자는 지금보다 8시간 뒤다 → 보내면 안 된다.
          · −08:00 으로 적힌 '1시간 뒤' — 벽시계 숫자는 지금보다 7시간 앞이다 → 보내야 한다.
        naive 로 읽어 UTC 로 보는 구현은 둘 다 틀린다. naive 로 읽어 **이 기계의** 로컬 시각과
        비교하는 구현은 기계의 오프셋 L 에 따라 갈리는데, 첫째는 L < 8 이면, 둘째는 L > −7 이면
        틀리므로 어느 시간대에서 돌려도 적어도 하나는 빨갛다. naive 와 aware 를 바로 비교하는
        구현은 TypeError → 둘째에서 요청이 없다."""
        now = datetime.now(UTC)
        cases = (
            ("expired, written +09:00", _expiry_text(now - timedelta(hours=1), 9), False),
            ("valid, written -08:00", _expiry_text(now + timedelta(hours=1), -8), True),
        )
        for name, text, should_send in cases:
            with self.subTest(expiry=name):
                r = _run_fetch(self, _secret(expiry=text))
                _assert_no_raise(self, r)
                if should_send:
                    self.assertTrue(r.server.requests, "유효한 토큰을 만료로 봤다: %s" % text)
                    self.assertIsNotNone(r.rows)
                else:
                    self.assertEqual(r.server.requests, [], "만료된 토큰을 보냈다: %s" % text)
                    self.assertIsNone(r.rows)

    def test_a_credential_without_expiry_is_sent(self):
        """expiry 가 없는 자격증명은 '이미 만료된' 것이 아니다 — 보내고 서버가 판단한다.
        Rival: expiry 없음을 만료로 봄(행 없음)."""
        r = _run_fetch(self, agy_secret(credential_obj(expiry=_MISSING)))
        _assert_no_raise(self, r)
        self.assertTrue(r.server.requests, "expiry 가 없다고 요청을 안 보냈다")
        _assert_rows(self, r.rows, [HEADLINE_ROW] + MODEL_ROWS + GROUP_ROWS)

    def test_off_macos_nothing_is_read_or_sent(self):
        """macOS 가 아니면 지금은 아무것도 하지 않는다 — 프로세스·네트워크 0, None.
        Rival: 플랫폼을 보지 않고 security 를 부름(윈도우·리눅스에 그런 명령은 없다)."""
        for plat in ("win32", "linux"):
            with self.subTest(platform=plat):
                r = _run_fetch(self, _secret(), platform=plat)
                _assert_no_raise(self, r)
                self.assertIsNone(r.rows)
                self.assertEqual(r.procs.security, [])
                self.assertEqual(r.procs.other, [])
                self.assertEqual(r.server.requests, [])

    def test_secrets_never_reach_logs_output_rows_or_status(self):
        """토큰·refresh 토큰·이메일·프로젝트 id 는 _dbg·stdout·stderr·logging·행·GEMINI_STATUS
        어디에도 없다 — 성공, 각 실패 경로 모두. 첫 단언(토큰이 실제로 Authorization 에 쓰였다)이
        없으면 읽지도 않는 구현이 통과한다. 프로젝트 id 는 계정에 묶인 식별자라 Codex 의 계정 id
        와 같이 다룬다(CLAUDE.md Privacy, tests/test_codex_usage.py 의 계정 id 규칙).
        Rivals: `_dbg("gemini fetch", headers)`; 요청 본문·응답 원문 로그; 예외 문구에 토큰;
        `print(cred)`; 행이나 상태에 프로젝트 id."""
        cases = (
            ("ok", None),
            ("load 401", {"loadCodeAssist": 401}),
            ("quota 403", {"retrieveUserQuota": 403}),
            ("quota 500", {"retrieveUserQuota": 500}),
            ("quota net", {"retrieveUserQuota": "net"}),
            ("quota garbage", {"retrieveUserQuota": "garbage"}),
            ("summary 500", {"retrieveUserQuotaSummary": 500}),
        )
        for name, fail in cases:
            with self.subTest(path=name):
                r = _run_fetch(self, _secret(), server=_FakeCloudCode(fail=fail))
                _assert_no_raise(self, r)
                self.assertTrue(r.server.requests, "요청이 없다 — 토큰을 쓰지도 않았다")
                self.assertEqual(r.server.requests[0].headers.get("authorization"),
                                 "Bearer " + TOKEN)
                for label, value in (("token", TOKEN), ("refresh token", REFRESH),
                                     ("email", EMAIL), ("project id", PROJECT)):
                    self.assertNotIn(value, r.log_text, "%s 가 로그·출력에 남았다" % label)
                    self.assertNotIn(value, repr(r.rows), "%s 가 행에 실렸다" % label)
                    self.assertNotIn(value, repr(r.status), "%s 가 상태에 남았다" % label)


if __name__ == "__main__":
    unittest.main()
