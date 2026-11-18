"""Gemini(agy) 키체인 조용히 — 리뷰 M1 게이팅 테스트. Verifier 작성, 구현 전.

TOK-44 리뷰(gemini-review)의 필수 수정 M1: e5cde29 의 `fetch_gemini_usage` 는 토큰이 멀쩡해도
180초마다 agy 키체인 비밀값을 다시 복호화하고(리뷰어 실측 시간당 20회), 프롬프트가 났을 때
멈추는 장치가 없다. 비밀값 복호화는 그 자체로 SecurityAgent 창의 기회다 — Claude 쪽이 v1.1.1 에서
같은 문제를 `_oauth_blob_noprompt` / KEYCHAIN_FACTS_TTL / KEYCHAIN_FACTS_MIN_INTERVAL /
`_keychain_prompt_allowed` 로 고쳤고(tests/test_keychain_quiet.py), 여기서는 그 규칙을 Gemini 에
건다. 이 파일은 TOK-44 의 함수에 대해 쓰였다(`_require` 가드 — TOK-47 브랜치에 아직 없으면 실패,
에러가 아니다).

── 계약 (Coordinator, M1) ──────────────────────────────────────────────────────────────

(a) 해석한 자격증명(토큰 + expiry)을 메모리에 기억한다. 키체인은 기억한 토큰이 만료 임박이거나,
    401 을 받았거나, 기억한 것이 없을 때만 다시 읽는다 — 그리고 **60초에 한 번보다 자주 읽지 않는다**.
(b) `security` 가 시간 초과(TimeoutExpired)하거나 사용자 취소(errSecUserCanceled → 종료 코드 128 /
    "User canceled")로 끝나면 자동 읽기를 멈춘다 — 사용자가 직접 누른 뒤(`_keychain_prompt_allowed()`
    가 참) 또는 재시작 전까지. 그리고 상태를 남긴다('자격증명 없음'으로 조용히 넘어가지 않는다).
(c) `keychain_locked()` 가 참인 동안에는, 기억한 자격증명이 아직 유효하면 그것을 계속 쓴다(행을
    잃지 않는다) — 리뷰 L1.
(d) 유효한 토큰으로 한 시간을 돌렸을 때 읽기 횟수는 '만료 임박' 주기 수준이어야 한다(시간당 몇 번),
    새로고침마다가 아니다.
TOK-47 배선(리뷰어 메모, 관찰 가능한 행동만):
(e) Gemini 를 숨기면(show_gemini False) Gemini 조회가 돌지 않는다 — `security` 를 띄우지 않는다.
(f) 느린 cloudcode-pa 가 Claude/Codex 행을 늦추지 않는다(Gemini 를 주 새로고침 경로 밖에서 받거나
    짧은 자기 시간 제한으로).

── 이 파일이 Developer 에게 거는 이름 (Verifier 제안 — 보고서에서 확인 요청) ──────────────────

  · 키체인 읽기가 멈췄다는 상태: `GEMINI_STATUS["last_error"] == "keychain_blocked"`.
  · '재시작'은 `_reset_keychain_quiet_state()` 다(이미 있는 함수, Claude 쪽 기억과 프롬프트 창을
    비운다). Gemini 의 기억한 자격증명과 멈춤 깃발도 여기서 비워야 한다 — 테스트 격리와 재시작
    경계가 같은 일이다.
  · '사용자가 직접 누름'은 `allow_keychain_prompt()` 다(이미 있음, `_keychain_prompt_allowed()` 를
    120초 동안 참으로).
  · 그 밖의 기억 장소 이름은 정하지 않는다. 다만 하네스는 이름에 `gemini` 가 든 모듈 dict 를 매
    테스트 전에 임포트 시점의 모양으로 되돌린다.

── 시계와 격리 ─────────────────────────────────────────────────────────────────────────

`claude_pet.time` 은 손으로 미는 시계, `claude_pet.datetime.now` 는 그 시계를 따른다(30초 새로고침을
한 시간씩 몇 초 만에 돌린다). `subprocess.run` 은 아무것도 실행하지 않는 기록기다 — agy 항목
(`-s gemini -a antigravity -w`)에만 합성 비밀값으로 답한다. Popen·os.system·ctypes.CDLL 은 막는다.
`keychain_locked` 는 늘 대역이다. cloudcode-pa 는 가짜 urlopen 이다 — 만료된 토큰과 거절 목록의
토큰에는 401. HOME 은 임시 디렉터리. 진짜 키체인·네트워크·`~/.gemini`·`~/.claude` 에 닿지 않는다.
(e)(f) 는 run_gui 의 새로고침 워커 `refresh_` 를 AST 로 꺼내 진짜 스레드로 돌린다(실시간, 몇 초).

기대 횟수는 계약 문장에서 계산했다 — 코드를 돌려서 얻지 않았다.
"""

import ast
import base64
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time as _real_time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime as _real_datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import claude_pet  # noqa: E402
except ImportError:
    from windows.win_core import import_core  # noqa: E402
    claude_pet = import_core()

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "claude_pet.py"
UTC = timezone.utc
T0 = 1_800_000_000.0
STEP = 30.0                      # 새로고침 간격(초) — run_gui 의 30초 타이머
PROJECT = "synthetic-project-0001"


def _require(name):
    value = getattr(claude_pet, name, None)
    if value is None:
        raise AssertionError(
            f"claude_pet.{name} 가 없다 — TOK-44 의 Gemini 리더가 이 브랜치에 아직 없거나 M1 이 구현되지 "
            "않았다. 이 파일은 구현 전에 쓰였고 지금 빨간 것이 정상이다.")
    return value


def _secret(token, expiry_epoch):
    exp = _real_datetime.fromtimestamp(expiry_epoch, UTC).isoformat()
    obj = {"token": {"access_token": token, "token_type": "Bearer",
                     "refresh_token": "synthetic-refresh", "expiry": exp, "expires_in": 3599},
           "auth_method": "consumer", "id_token_email": "synthetic@example.invalid"}
    return "go-keyring-base64:" + base64.b64encode(json.dumps(obj).encode()).decode()


class _Clock:
    def __init__(self, now):
        self.now = float(now)

    def time(self):
        return self.now

    def __getattr__(self, name):
        return getattr(_real_time, name)


def _arg_after(argv, flag):
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


class _Keychain:
    """subprocess.run 의 대역. agy 항목에만 답한다. mode: ok | missing | timeout | cancel."""

    def __init__(self, clock):
        self.clock = clock
        self.token = None
        self.expiry = None
        self.mode = "ok"
        self.reads = []          # agy 항목을 읽은 시각(시계 기준)
        self.other = []
        self.blocked = []

    def hold(self, token, expiry):
        self.token, self.expiry = token, float(expiry)

    def run(self, argv, *a, **k):
        if isinstance(argv, (str, bytes)):
            argv = str(argv).split()
        argv = [str(x) for x in argv]
        text = bool(k.get("text") or k.get("universal_newlines") or k.get("encoding"))
        conv = (lambda s: s) if text else (lambda s: s.encode())
        agy = (argv and os.path.basename(argv[0]) == "security"
               and "find-generic-password" in argv
               and _arg_after(argv, "-s") == "gemini" and _arg_after(argv, "-a") == "antigravity")
        if not agy:
            self.other.append(argv[:2])
            res = subprocess.CompletedProcess(argv, 1, conv(""), conv(""))
        else:
            self.reads.append(self.clock.time())
            if self.mode == "timeout":
                raise subprocess.TimeoutExpired(argv, k.get("timeout") or 5)
            if self.mode == "cancel":
                res = subprocess.CompletedProcess(
                    argv, 128, conv(""), conv("security: SecKeychainSearchCopyNext: "
                                              "User canceled the operation.\n"))
            elif self.mode == "missing" or self.token is None:
                res = subprocess.CompletedProcess(
                    argv, 44, conv(""), conv("security: SecKeychainSearchCopyNext: The specified "
                                             "item could not be found in the keychain.\n"))
            else:
                res = subprocess.CompletedProcess(
                    argv, 0, conv(_secret(self.token, self.expiry) + "\n"), conv(""))
        if k.get("check") and res.returncode:
            raise subprocess.CalledProcessError(res.returncode, argv, res.stdout, res.stderr)
        return res

    def popen(self, *a, **k):
        self.blocked.append("Popen")
        raise OSError("blocked")

    def system(self, *a, **k):
        self.blocked.append("os.system")
        return 1

    def cdll(self, name, *a, **k):
        self.blocked.append("CDLL:%s" % name)
        raise OSError("blocked")


class _Resp(io.BytesIO):
    status = 200

    def getcode(self):
        return 200


class _CloudCode:
    """cloudcode-pa 대역. 토큰마다 만료 시각을 알고, 만료됐거나 rejected 에 든 토큰엔 401.
    hang 이 Event 면 응답 전에 그것을 기다린다(urlopen 의 timeout 을 지킨다 — 넘으면 socket.timeout)."""

    def __init__(self, clock, keychain):
        self.clock = clock
        self.keychain = keychain
        self.expiry_of = {}
        self.rejected = set()
        self.requests = []       # (시각, 엔드포인트, 토큰)
        self.hang = None

    def __call__(self, req, data=None, timeout=None, *a, **kw):
        url = req.full_url
        endpoint = urllib.parse.urlsplit(url).path.rsplit(":", 1)[-1]
        headers = {k.lower(): v for k, v in req.header_items()}
        token = (headers.get("authorization") or "")[len("Bearer "):]
        self.requests.append((self.clock.time(), endpoint, token))
        if self.hang is not None:
            if not self.hang.wait(timeout if timeout else 60):
                raise socket.timeout("synthetic hang")
        exp = self.expiry_of.get(token)
        if token in self.rejected or exp is None or exp <= self.clock.time():
            raise urllib.error.HTTPError(url, 401, "synthetic 401", {}, io.BytesIO(b"{}"))
        if endpoint == "loadCodeAssist":
            body = {"cloudaicompanionProject": PROJECT}
        elif endpoint == "retrieveUserQuota":
            body = {"buckets": [{"modelId": "gemini-3-flash", "tokenType": "WTUS",
                                 "remainingFraction": 0.5,
                                 "resetTime": "2027-01-15T08:00:00Z"}]}
        elif endpoint == "retrieveUserQuotaSummary":
            body = {"groups": []}
        else:
            raise urllib.error.HTTPError(url, 404, "nope", {}, io.BytesIO(b"{}"))
        return _Resp(json.dumps(body).encode())


def _gemini_dicts():
    return {n: v for n, v in vars(claude_pet).items()
            if isinstance(v, dict) and "gemini" in n.lower()}


_PRISTINE = {n: dict(v) for n, v in _gemini_dicts().items()}


class _QuietCase(unittest.TestCase):
    """시계·키체인·서버·격리. self.issue(token, expiry) 로 agy 가 키체인에 토큰을 쓴 것을 흉내 낸다."""

    real_clock = False

    def setUp(self):
        _require("fetch_gemini_usage")
        self.home = tempfile.mkdtemp(prefix="claudepet-gkq-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        env.pop("CLAUDE_PET_DEBUG", None)
        self._patch(mock.patch.dict(os.environ, env, clear=True))
        self.clock = _Clock(T0)
        clock = self.clock

        class _DT(_real_datetime):
            @classmethod
            def now(cls, tz=None):
                return _real_datetime.fromtimestamp(clock.time(), tz)

        if not self.real_clock:
            self._patch(mock.patch.object(claude_pet, "time", self.clock))
            self._patch(mock.patch.object(claude_pet, "datetime", _DT))
        self.kc = _Keychain(self.clock if not self.real_clock else _real_time)
        self.server = _CloudCode(self.clock if not self.real_clock else _real_time, self.kc)
        self.locked = False
        self._patch(mock.patch.object(sys, "platform", "darwin"))
        self._patch(mock.patch.object(claude_pet.subprocess, "run", self.kc.run))
        self._patch(mock.patch.object(claude_pet.subprocess, "Popen", self.kc.popen))
        self._patch(mock.patch.object(claude_pet.os, "system", self.kc.system))
        self._patch(mock.patch.object(claude_pet.ctypes, "CDLL", self.kc.cdll))
        self._patch(mock.patch.object(claude_pet, "keychain_locked", lambda: self.locked,
                                      create=True))
        self._patch(mock.patch.object(claude_pet.urllib.request, "urlopen", self.server))
        self._patch(mock.patch.object(claude_pet, "_dbg", lambda *a, **k: None))
        self._patch(mock.patch("socket.create_connection",
                               side_effect=AssertionError("테스트가 네트워크에 나가려 했다")))
        for name, d in _gemini_dicts().items():
            snap = dict(d)
            self.addCleanup(lambda d=d, snap=snap: (d.clear(), d.update(snap)))
            if name in _PRISTINE:
                d.clear()
                d.update(_PRISTINE[name])
        status = getattr(claude_pet, "GEMINI_STATUS", None)
        if isinstance(status, dict):
            status.update({"auth_error": False, "last_error": None})
        self._restart()
        self.addCleanup(self._restart)

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def _restart(self):
        fn = getattr(claude_pet, "_reset_keychain_quiet_state", None)
        if fn is not None:
            fn()

    def restart_app(self):
        """앱 재시작: 키체인 조용히 상태(_reset_keychain_quiet_state)와 Gemini 의 모듈 상태가 처음으로."""
        self._restart()
        for name, d in _gemini_dicts().items():
            if name in _PRISTINE:
                d.clear()
                d.update(_PRISTINE[name])
        status = getattr(claude_pet, "GEMINI_STATUS", None)
        if isinstance(status, dict):
            status.update({"auth_error": False, "last_error": None})

    def user_refresh(self):
        """사용자가 펫을 더블클릭해 새로 고친다 — Claude 쪽과 같은 두 가지: 프롬프트 창을 열고
        (allow_keychain_prompt) 캐시 시각을 0 으로(즉시 재조회). Gemini 캐시는 이름에 gemini 가 든
        dict 의 "t" 다(TOK-44 의 _gemini_cache 모양)."""
        claude_pet.allow_keychain_prompt()
        for _name, d in _gemini_dicts().items():
            if "t" in d:
                d["t"] = 0.0

    def issue(self, token, expiry):
        """agy 가 새 토큰을 키체인에 쓴다(서버도 그 토큰을 안다)."""
        self.kc.hold(token, expiry)
        self.server.expiry_of[token] = float(expiry)

    def fetch(self):
        return claude_pet.fetch_gemini_usage()

    def run_until(self, end, step=STEP, before=None):
        """시계를 step 씩 밀며 fetch 한다 → [(시각, 행)]."""
        out = []
        while self.clock.time() <= end:
            if before:
                before(self.clock.time())
            out.append((self.clock.time(), self.fetch()))
            self.clock.now += step
        return out

    def status(self):
        return dict(getattr(claude_pet, "GEMINI_STATUS", {}) or {})


def _gaps(times):
    return [b - a for a, b in zip(times, times[1:])]


# ═══════════════════════════ (a)(d) 기억하고, 만료 임박에만 다시 읽는다 ═══════════════════════════


class RememberedCredentialTests(_QuietCase):

    def test_a_valid_token_is_read_once_not_every_refresh(self):
        """두 시간짜리 토큰으로 한 시간(30초 새로고침 121번): 키체인 읽기 ≤ 3, 행은 한 번도 안 빈다.
        3 은 첫 읽기 + Claude 쪽 KEYCHAIN_FACTS_TTL(1800초) 재확인을 허용한 상한이다(만료 임박은 이
        한 시간 안에 오지 않는다 — 토큰은 T0+2h 에 만료).
        Rivals: e5cde29 — 캐시(180초)가 풀릴 때마다 읽음(=21회); TTL 을 짧게(600초 → 7회)."""
        self.issue("tok-A", T0 + 7200)
        out = self.run_until(T0 + 3600)
        self.assertTrue(all(rows for _t, rows in out), "유효한 토큰인데 행이 빈 새로고침이 있다")
        self.assertGreaterEqual(len(self.kc.reads), 1)
        self.assertLessEqual(len(self.kc.reads), 3,
                             "한 시간에 키체인을 %d번 읽었다(시각 %r)" % (
                                 len(self.kc.reads), [t - T0 for t in self.kc.reads]))

    def test_hourly_tokens_are_reread_near_expiry_at_most_once_a_minute(self):
        """agy 가 떠 있는 두 시간 + agy 를 닫은 한 시간. 토큰은 한 시간짜리, agy 는 만료 5분 전에 새
        토큰을 쓴다. 첫 토큰은 T0+600 에 만료.
          · 떠 있는 동안: 행이 끊기지 않고, 보낸 토큰은 언제나 만료 전이고, 한 시간 창마다 읽기 ≤ 6,
            두 읽기 사이 ≥ 60초.
          · 닫은 뒤(마지막 토큰 만료 후): 만료된 토큰은 보내지 않고(last_error "expired"), 다시 읽기는
            여전히 ≥ 60초 간격.
        Rivals: e5cde29(180초마다 읽음 → 시간당 20); 만료 임박에서 60초 하한 없이 매 새로고침(30초)
        읽기; 기억한 토큰을 끝까지 써서 만료 뒤 401(새 토큰을 안 읽음)."""
        tokens = {}

        def agy(now):
            # 열려 있는 동안(T0+2h 이전)만 회전한다. k 번째 토큰은 T0+600+3600k 에 만료.
            k = 0
            while T0 + 600 + 3600 * k - 300 <= now and T0 + 600 + 3600 * k - 300 < T0 + 7200:
                k += 1
            if k not in tokens:
                tokens[k] = ("tok-%d" % k, T0 + 600 + 3600 * k)
                self.issue(*tokens[k])

        open_end = T0 + 7200
        out = self.run_until(open_end, before=agy)
        self.assertTrue(all(rows for _t, rows in out),
                        "agy 가 떠 있는데 행이 빈 새로고침: %r" % [t - T0 for t, r in out if not r])
        for t, _ep, tok in self.server.requests:
            self.assertGreater(self.server.expiry_of.get(tok, 0), t, "만료된 토큰을 보냈다")
        reads = list(self.kc.reads)
        self.assertTrue(all(g >= 60 for g in _gaps(reads)),
                        "읽기 간격이 60초보다 짧다: %r" % _gaps(reads))
        for start in range(int(T0), int(open_end) - 3600 + 1, 300):
            n = sum(1 for r in reads if start <= r < start + 3600)
            self.assertLessEqual(n, 6, "한 시간 창(%d~)에 읽기 %d번" % (start - T0, n))
        # agy 를 닫았다 — 마지막 토큰이 만료되고 나서 한 시간 더.
        last_exp = max(e for _tok, e in tokens.values())
        self.clock.now = max(self.clock.now, last_exp + 1)
        n_req = len(self.server.requests)
        tail = self.run_until(self.clock.now + 3600)
        self.assertTrue(all(rows is None for _t, rows in tail))
        self.assertEqual(self.server.requests[n_req:], [], "만료된 토큰을 보냈다")
        self.assertEqual(self.status().get("last_error"), "expired")
        self.assertTrue(all(g >= 60 for g in _gaps(self.kc.reads)),
                        "만료 뒤 다시 읽기가 60초보다 잦다: %r" % _gaps(self.kc.reads))

    def test_after_a_401_the_keychain_is_read_again(self):
        """15분 동안은 첫 읽기 하나뿐(기억). 그 사이 agy 가 토큰을 B 로 바꾸고 서버가 A 를 거절(401)하면,
        다음 4분 안에 키체인을 다시 읽어 B 로 행을 되찾는다. 다시 읽기도 60초 간격을 지킨다.
        Rivals: e5cde29(15분에 5번 읽음); 기억한 A 를 만료까지 고집(401 이 계속, 행 없음)."""
        self.issue("tok-A", T0 + 7200)
        self.run_until(T0 + 900)
        self.assertEqual(len(self.kc.reads), 1, "15분 동안 키체인을 %d번 읽었다" % len(self.kc.reads))
        self.issue("tok-B", T0 + 9000)
        self.server.rejected.add("tok-A")
        start = self.clock.time()
        out = self.run_until(start + 240)
        self.assertTrue(any(tok == "tok-B" for _t, _e, tok in self.server.requests),
                        "401 뒤에 키체인을 다시 읽지 않았다")
        self.assertTrue(out[-1][1], "401 뒤 4분이 지나도 행이 돌아오지 않았다")
        self.assertTrue(all(g >= 60 for g in _gaps(self.kc.reads)), _gaps(self.kc.reads))


    def test_rereads_stay_a_minute_apart_even_when_the_usage_cache_is_cleared(self):
        """30초 타이머와 180/60초 캐시만으로는 60초 하한이 드러나지 않는다 — 캐시가 늘 그보다 느리다.
        그래서 캐시를 일부러 비운다(더블클릭 새로고침·설정 저장처럼 캐시 시각을 0 으로 만드는 경로).
        만료 임박(100초 남음, agy 는 아직 새 토큰을 안 씀)인 토큰으로 10초마다 캐시를 비우고 조회해도
        키체인 읽기는 첫 60초 동안 1번, 다음 60초 동안 많아야 1번 더.
        Rivals: 60초 하한 없음(만료 임박이면 조회마다 읽음 → 6번); e5cde29(조회마다 읽음)."""
        self.issue("tok-A", T0 + 100)
        start = self.clock.time()

        def clear(_now):
            for _name, d in _gemini_dicts().items():
                if "t" in d:
                    d["t"] = 0.0

        self.run_until(start + 50, step=10.0, before=clear)
        self.assertEqual(len(self.kc.reads), 1,
                         "60초 안에 키체인을 %d번 읽었다" % len(self.kc.reads))
        self.clock.now = start + 60
        self.run_until(start + 110, step=10.0, before=clear)
        self.assertLessEqual(len(self.kc.reads), 2)
        self.assertTrue(all(g >= 60 for g in _gaps(self.kc.reads)), _gaps(self.kc.reads))


# ═══════════════════════════ (b) 시간 초과·취소면 사용자가 누를 때까지 멈춘다 ═══════════════════════════


class StopOnPromptTests(_QuietCase):

    def test_a_timeout_or_cancel_stops_automatic_reads_until_the_user_acts(self):
        """첫 읽기가 시간 초과(프롬프트가 떠 있는 동안 security 가 기다린 모양)나 사용자 취소(128)면:
          · 10분 동안 자동 읽기 0번(첫 읽기 뒤), 행 None, 상태 last_error "keychain_blocked"
            ('자격증명 없음'과 구별된다 — 그쪽은 last_error 를 이렇게 두지 않는다).
          · 사용자가 직접 누르면(allow_keychain_prompt) 2분 안에 다시 읽고 행이 돌아온다.
          · 다시 막힌 뒤 재시작(_reset_keychain_quiet_state)해도 다시 읽는다.
        Rivals: e5cde29(실패를 '없음'으로 보고 60초마다 다시 security — 프롬프트가 계속 뜬다);
        멈추되 상태를 안 남김; 사용자가 눌러도 안 풀림."""
        _require("allow_keychain_prompt")
        for mode in ("timeout", "cancel"):
            with self.subTest(mode=mode):
                self.setUp_fresh()
                self.issue("tok-A", self.clock.time() + 7200)
                self.kc.mode = mode
                out = self.run_until(self.clock.time() + 600)
                self.assertEqual(len(self.kc.reads), 1,
                                 "멈추지 않았다 — %s 뒤 %d번 더 읽었다" % (mode, len(self.kc.reads) - 1))
                self.assertTrue(all(rows is None for _t, rows in out))
                self.assertEqual(self.status().get("last_error"), "keychain_blocked")
                # 사용자가 직접 누른다(더블클릭 새로고침이 하는 일). 프롬프트 창(120초) 안에 읽어야 한다.
                self.kc.mode = "ok"
                self.user_refresh()
                out = self.run_until(self.clock.time() + 120)
                self.assertGreaterEqual(len(self.kc.reads), 2, "사용자가 눌렀는데 다시 읽지 않았다")
                self.assertTrue(out[-1][1], "사용자가 누른 뒤 행이 돌아오지 않았다")
                # 다시 막혔다가, 이번엔 재시작으로 푼다.
                self.kc.mode = mode
                self.server.rejected.add("tok-A")          # 401 → 다시 읽기 → 막힘
                self.run_until(self.clock.time() + 300)
                n = len(self.kc.reads)
                self.run_until(self.clock.time() + 600)
                self.assertEqual(len(self.kc.reads), n, "다시 막힌 뒤에도 자동으로 읽었다")
                self.kc.mode = "ok"
                self.issue("tok-B", self.clock.time() + 7200)
                self.restart_app()
                out = self.run_until(self.clock.time() + 120)
                self.assertGreater(len(self.kc.reads), n, "재시작 뒤에도 읽지 않았다")
                self.assertTrue(out[-1][1])

    def setUp_fresh(self):
        """subTest 사이의 재시작: 기억·깃발·캐시·기록을 비운다."""
        self.restart_app()
        self.kc.reads.clear()
        self.server.rejected.clear()
        self.clock.now += 10_000


# ═══════════════════════════ (c) 잠긴 키체인에서도 기억한 토큰을 쓴다 ═══════════════════════════


class LockedKeychainTests(_QuietCase):

    def test_while_locked_the_remembered_token_keeps_the_rows(self):
        """읽어 둔 토큰이 유효하면 키체인이 잠겨 있는 20분 동안 행이 이어지고 security 는 0번이다.
        잠긴 채 그 토큰이 만료되면 보내지 않는다(None, "expired") — 역시 security 없이.
        Rivals: e5cde29(잠기면 '자격증명 없음' → 행이 사라짐, 리뷰 L1); 잠긴 키체인에 security 를 부름
        ('키체인 암호' 창)."""
        self.issue("tok-A", T0 + 3000)
        self.assertTrue(self.fetch(), "첫 조회가 행을 내야 이 테스트가 뜻이 있다")
        n = len(self.kc.reads)
        self.locked = True
        self.clock.now += STEP
        out = self.run_until(T0 + 1200)
        self.assertEqual(len(self.kc.reads), n, "잠긴 키체인에 security 를 불렀다")
        self.assertTrue(all(rows for _t, rows in out), "잠겼다고 행이 사라졌다")
        self.clock.now = T0 + 3001
        n_req = len(self.server.requests)
        out = self.run_until(T0 + 3600)
        self.assertEqual(len(self.kc.reads), n)
        self.assertTrue(all(rows is None for _t, rows in out))
        self.assertEqual(self.server.requests[n_req:], [], "만료된 토큰을 보냈다")
        self.assertEqual(self.status().get("last_error"), "expired")


# ═══════════════════════════ (e)(f) TOK-47 배선 — 새로고침 워커 ═══════════════════════════


_STUB_NAMES = ("fetch_exact_usage", "fetch_codex_usage", "compute_usage", "model_keyword_from_rows",
               "parse_codex_entries", "learn_server_limits", "claude_spikes", "codex_spikes",
               "fetch_api_cost_today", "fetch_api_cost_month", "fetch_codex_cost_today",
               "fetch_codex_cost_month", "compute_codex_onboard_state", "read_codex_token",
               "_find_codex_cli", "codex_home_exists", "compute_onboard_state",
               "claude_token_present", "session_reset_jump")


def _refresh_worker(test, state, claude_rows, codex_rows):
    """run_gui 안의 `refresh_` 를 꺼내 손으로 만든 scope 에 올린다. Claude/Codex 쪽 조회는 즉시
    답하는 대역이고, Gemini 쪽은 **진짜** 코드(모듈의 fetch_gemini_usage 와 그것이 부르는 것)다 —
    키체인·서버 대역은 _QuietCase 가 모듈에 깔아 둔 것이다."""
    from test_companion_motion import gui_functions

    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    gui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")
    found = [n for n in ast.walk(gui) if isinstance(n, ast.FunctionDef) and n.name == "refresh_"]
    test.assertEqual(len(found), 1, "run_gui 에 refresh_ 가 정확히 하나여야 한다")
    scope = dict(vars(claude_pet))
    now_utc = _real_datetime.now(UTC)
    scope.update({
        "state": state,
        "fetch_exact_usage": lambda: claude_rows,
        "fetch_codex_usage": lambda: codex_rows,
        "compute_usage": lambda **k: {"now": now_utc, "rows": []},
        "model_keyword_from_rows": lambda rows: None,
        "parse_codex_entries": lambda since: [],
        "learn_server_limits": lambda *a, **k: None,
        "claude_spikes": lambda *a, **k: {},
        "codex_spikes": lambda *a, **k: {},
        "fetch_api_cost_today": lambda: None, "fetch_api_cost_month": lambda: None,
        "fetch_codex_cost_today": lambda: None, "fetch_codex_cost_month": lambda: None,
        "compute_codex_onboard_state": lambda *a, **k: None,
        "read_codex_token": lambda *a, **k: None,
        "_find_codex_cli": lambda: None, "codex_home_exists": lambda *a, **k: False,
        "compute_onboard_state": lambda *a, **k: None,
        "claude_token_present": lambda: False,
        "session_reset_jump": lambda *a, **k: False,
        "_recovery_step": lambda *a, **k: None,
        "_run_update_check": lambda *a, **k: None,
        "set_override": lambda *a, **k: None,
        "_upd_cache": {"t": _real_time.time(), "busy": False},
        "OAUTH_EXTRA": {"credit": None},
    })
    # refresh_ 가 새로 부르는 run_gui 수준의 닫힌 함수(예: Gemini 를 따로 받는 도우미)도 같이 올린다.
    gui_defs = {n.name for n in gui.body if isinstance(n, ast.FunctionDef)}
    loads = {n.id for n in ast.walk(found[0]) if isinstance(n, ast.Name)
             and isinstance(n.ctx, ast.Load)}
    extra = sorted((loads & gui_defs) - set(scope))
    if extra:
        gui_functions(test, tuple(extra), scope)
    node = found[0]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["refresh_"]


def _wait(cond, seconds):
    end = _real_time.time() + seconds
    while _real_time.time() < end:
        if cond():
            return True
        _real_time.sleep(0.02)
    return cond()


class RefreshWiringTests(_QuietCase):
    real_clock = True

    def setUp(self):
        super().setUp()
        saved = dict(claude_pet.RUNTIME)
        self.addCleanup(lambda: (claude_pet.RUNTIME.clear(), claude_pet.RUNTIME.update(saved)))
        claude_pet.RUNTIME.update({"mode": "sub", "show_claude": True,
                                   "claude_gauges": ["session", "weekly"], "show_codex": True,
                                   "codex_mode": "sub", "codex_gauges": ["session", "weekly"],
                                   "gemini_gauges": ["gemini"]})
        self.issue("tok-A", _real_time.time() + 7200)

    def drive(self, show_gemini):
        claude_pet.RUNTIME["show_gemini"] = show_gemini
        state = {"oauth": None, "codex": None, "gemini": None, "stats": None,
                 "refresh_generation": 0, "repaint": False}
        claude = [("session", 10.0, None, None)]
        codex = [("codex_weekly", 20.0, None, None)]
        refresh = _refresh_worker(self, state, claude, codex)
        refresh(None, None)
        return state, claude, codex

    def test_hidden_gemini_spawns_no_security_and_shown_gemini_is_fetched(self):
        """숨긴 Gemini: 새로고침이 끝나도 agy 키체인 읽기 0번, cloudcode-pa 요청 0번. 보이는 Gemini:
        같은 새로고침이 키체인을 읽고 state["gemini"] 에 행을 넣는다.
        숨긴 쪽은 구현 전에도 초록이다(아무도 Gemini 를 부르지 않는다) — 보이는 쪽이 빨강의 근거다.
        Rivals: 표시 설정과 상관없이 매번 fetch_gemini_usage(숨긴 사용자의 키체인을 30초마다 두드림);
        새로고침이 Gemini 를 아예 안 받음(행이 영영 None)."""
        state, claude, _codex = self.drive(show_gemini=False)
        self.assertTrue(_wait(lambda: state["oauth"] == claude, 3.0), "새로고침이 끝나지 않았다")
        _real_time.sleep(0.3)
        self.assertEqual(self.kc.reads, [], "숨긴 Gemini 때문에 security 를 띄웠다")
        self.assertEqual(self.server.requests, [])
        state, _claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(_wait(lambda: bool(state.get("gemini")), 5.0),
                        "보이는 Gemini 를 새로고침이 받지 않았다(state['gemini'] 가 비어 있다)")
        self.assertGreaterEqual(len(self.kc.reads), 1)
        self.assertEqual(state["gemini"][0][0], "gemini")

    def test_a_hanging_cloudcode_does_not_hold_back_claude_and_codex(self):
        """cloudcode-pa 가 응답하지 않는 동안에도 Claude/Codex 행은 3초 안에 state 에 들어간다.
        서버가 풀리면 Gemini 행도 들어온다. (주 경로 밖에서 받든, 세 요청 합쳐 3초 안에 끝나는 짧은
        시간 제한이든 통과한다 — 가짜 서버는 urlopen 의 timeout 을 지킨다.)
        구현 전에는 Gemini 를 안 받으니 앞 절반은 초록이다 — 뒤 절반(행이 들어옴)이 빨강의 근거다.
        Rivals: Gemini 를 같은 패스에서 10초 timeout 으로 받은 뒤에야 commit(최대 30초 동안 Claude/Codex
        가 옛 값); Gemini 를 아예 안 받음."""
        self.server.hang = threading.Event()
        self.addCleanup(self.server.hang.set)
        state, claude, codex = self.drive(show_gemini=True)
        self.assertTrue(_wait(lambda: state["oauth"] == claude and state["codex"] == codex, 3.0),
                        "cloudcode-pa 가 멈춘 동안 Claude/Codex 행이 3초 안에 들어오지 않았다")
        self.server.hang.set()
        # 풀린 뒤에는 다음 새로고침(또는 진행 중인 받기)이 Gemini 행을 넣는다.
        got = _wait(lambda: bool(state.get("gemini")), 3.0)
        if not got:
            for name, d in _gemini_dicts().items():
                if "t" in d:
                    d["t"] = 0.0           # 실패 캐시를 건너뛰고 한 번 더(시간 제한 설계)
            refresh = _refresh_worker(self, state, claude, codex)
            refresh(None, None)
            got = _wait(lambda: bool(state.get("gemini")), 5.0)
        self.assertTrue(got, "서버가 풀린 뒤에도 Gemini 행이 들어오지 않았다")


if __name__ == "__main__":
    unittest.main()
