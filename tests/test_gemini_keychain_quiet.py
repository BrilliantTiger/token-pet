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
        self.timeouts = []       # 그 읽기마다 subprocess.run 에 준 timeout
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
            self.timeouts.append(k.get("timeout"))
            if self.mode == "timeout":
                raise subprocess.TimeoutExpired(argv, k.get("timeout") or 5)
            if self.mode == "deny":
                # errSecAuthFailed(-25293) — 사용자가 '거부'를 눌렀다. security 의 종료 코드는 하위 바이트 51.
                res = subprocess.CompletedProcess(
                    argv, 51, conv(""), conv("security: SecKeychainSearchCopyNext: The user name or "
                                             "passphrase you entered is not correct.\n"))
            elif self.mode == "cancel":
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
        self.summary = {"groups": []}
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
            body = self.summary
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
        # 만료 뒤 120초 유예(Coordinator 결정 2026-11-18, AgyLazyRefreshTests 머리말) 동안은 마지막 행이
        # 남을 수 있다. 유예 + 한 번의 60초 재시도(180초)가 지나면 빈 행이어야 한다.
        self.assertTrue(all(rows is None for t, rows in tail if t >= last_exp + 180),
                        "agy 를 닫고 만료 180초가 지나도 옛 행이 남았다")
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
        """첫 읽기가 시간 초과(프롬프트가 떠 있는 동안 security 가 기다린 모양), 사용자 취소(128), 사용자
        거부(51 = errSecAuthFailed 의 하위 바이트, 리뷰 2차 R2-1)면:
          · 10분 동안 자동 읽기 0번(첫 읽기 뒤), 행 None, 상태 last_error "keychain_blocked"
            ('자격증명 없음'과 구별된다 — 그쪽은 last_error 를 이렇게 두지 않는다).
          · 사용자가 직접 누르면(allow_keychain_prompt) 2분 안에 다시 읽고 행이 돌아온다.
          · 다시 막힌 뒤 재시작(_reset_keychain_quiet_state)해도 다시 읽는다.
        Rivals: e5cde29(실패를 '없음'으로 보고 60초마다 다시 security — 프롬프트가 계속 뜬다);
        멈추되 상태를 안 남김; 사용자가 눌러도 안 풀림."""
        _require("allow_keychain_prompt")
        for mode in ("timeout", "cancel", "deny"):
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


class KeychainReadPolicyTests(_QuietCase):
    """리뷰 2차(R2-2·R2-3) — 사용자가 직접 다시 시도한 읽기의 시간 제한과, agy 가 없는 Mac 의 물러서기."""

    def test_a_user_initiated_read_waits_long_and_an_automatic_one_does_not(self):
        """자동 읽기는 짧은 timeout(60초 미만 — 30초 새로고침 워커를 붙들지 않게), 사용자가 직접 누른 뒤의
        읽기(_keychain_prompt_allowed() 참)는 60초 이상(_token_from_cli 처럼 — 사람이 프롬프트에 답할 시간).
        자동 값 자체(5초)는 고정하지 않는다.
        Rivals: 8eb4ccb(언제나 5초 — 사용자가 프롬프트에 답하는 사이 시간 초과로 또 막힘); 언제나 60초
        (자동 읽기가 프롬프트 앞에서 1분씩 멈춤)."""
        self.issue("tok-A", T0 + 7200)
        self.kc.mode = "timeout"
        self.fetch()
        self.assertEqual(len(self.kc.timeouts), 1)
        auto = self.kc.timeouts[0]
        self.assertIsInstance(auto, (int, float), "자동 읽기에 timeout 이 없다")
        self.assertLess(auto, 60, "자동 읽기의 timeout 이 %r초다" % auto)
        self.clock.now += 600
        self.kc.mode = "ok"
        self.user_refresh()
        rows = self.fetch()
        self.assertEqual(len(self.kc.timeouts), 2, "사용자가 누른 뒤 바로 읽지 않았다")
        self.assertGreaterEqual(self.kc.timeouts[1] or 0, 60,
                                "사용자가 시작한 읽기의 timeout 이 %r초다" % self.kc.timeouts[1])
        self.assertTrue(rows)

    def test_a_mac_without_agy_backs_off_and_a_click_still_reads(self):
        """항목 없음(security 종료 44 = errSecItemNotFound): 자동 다시 읽기는 1800초 이상 간격 — 두 시간 동안
        어느 한 시간 창에도 3번 이하. 사용자가 누르면 그 조회에서 바로 읽고, 그새 항목이 생겼으면 행이 나온다.
        누르지 않아도 항목이 생기면 다음 물러서기 읽기(≤ 1800초 + 한 번의 조회 주기) 안에 잡힌다. 잡힌 뒤로는
        보통 일정(유효한 토큰 → 한 시간에 3번 이하).
        Rivals: 8eb4ccb(기억이 없으면 조회마다 = 180초마다 security — agy 없는 Mac 에서 시간당 20번);
        물러서는 동안 사용자 클릭도 무시."""
        self.kc.mode = "missing"
        out = self.run_until(T0 + 7200)
        reads = list(self.kc.reads)
        self.assertTrue(all(rows is None for _t, rows in out))
        self.assertTrue(all(g >= 1800 for g in _gaps(reads)), "물러서기 간격: %r" % _gaps(reads))
        for start in range(int(T0), int(T0 + 7200) - 3600 + 1, 300):
            n = sum(1 for r in reads if start <= r < start + 3600)
            self.assertLessEqual(n, 3, "agy 없는 Mac 에서 한 시간(%d~)에 security %d번" % (start - T0, n))
        # 사용자가 agy 에 로그인하고 펫을 누른다 — 그 조회에서 바로 읽는다. 60초 하한은 클릭에도 그대로라
        # (계약 4) 마지막 물러서기 읽기에서 2분 뒤에 누른다.
        self.clock.now = max(self.clock.now, reads[-1] + 120)
        self.kc.mode = "ok"
        self.issue("tok-A", self.clock.time() + 7200)
        n = len(self.kc.reads)
        self.user_refresh()
        rows = self.fetch()
        self.assertEqual(len(self.kc.reads), n + 1, "사용자가 눌렀는데 바로 읽지 않았다")
        self.assertTrue(rows)
        n = len(self.kc.reads)
        self.clock.now += STEP
        out = self.run_until(self.clock.time() + 3600)
        self.assertTrue(all(r for _t, r in out))
        self.assertLessEqual(len(self.kc.reads) - n, 3, "잡힌 뒤에도 자주 읽는다")
        # 다시: 누르지 않아도 항목이 생기면 물러서기 읽기에서 잡힌다.
        self.restart_app()
        self.kc.reads.clear()
        self.clock.now += 10_000
        self.kc.mode = "missing"
        start = self.clock.time()
        self.run_until(start + 600)
        self.assertEqual(len(self.kc.reads), 1)
        self.kc.mode = "ok"
        self.issue("tok-B", start + 7200)
        out = self.run_until(start + 1800 + 180 + 60)
        self.assertTrue(out[-1][1], "항목이 생겼는데 물러서기 읽기에서도 잡지 못했다")
        self.assertTrue(all(g >= 1800 for g in _gaps(self.kc.reads[:2])), _gaps(self.kc.reads))


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
        # 만료 뒤 120초 유예(AgyLazyRefreshTests 머리말) — 그 뒤(+180초)로는 빈 행.
        self.assertTrue(all(rows is None for t, rows in out if t >= T0 + 3000 + 180),
                        "잠긴 채 만료되고 180초가 지나도 옛 행이 남았다")
        self.assertEqual(self.server.requests[n_req:], [], "만료된 토큰을 보냈다")
        self.assertEqual(self.status().get("last_error"), "expired")


# ═══════════════════════════ agy 의 늦은 갱신 — 만료 직후의 유예 ═══════════════════════════
#
# 관측(Coordinator, 2026-11-18, 이 저장소 주인의 Mac 한 대, agy 1.5.10 실행 중, 키체인 항목의 mdat 를
# 비밀값을 읽지 않고 본 것): 항목의 수정 시각 05:06:25Z, 저장된 토큰의 만료 06:06:24Z — 즉 agy 는 **이전
# 토큰의 만료(05:06:24Z) 약 1초 뒤에** 새 토큰을 썼다. 같은 날 앞선 관측(만료 12:05→13:06→14:06→15:06
# KST)도 '만료 무렵에 갱신'과 맞는다. 표본은 한 기기·하루다 — agy 가 만료 **뒤에** 쓴다는 것은 관측이지
# 보장이 아니다. 그래서 아래 게이트는 1초 하나가 아니라 1·10·45초 뒤를 함께 본다.
#
# 계약(Coordinator 결정): (1) 기억한 만료 300초 전부터 만료 600초 뒤까지는 60초 하한으로 다시 읽는다;
# (2) 기억한 토큰이 만료된 뒤 120초까지는, 마지막 조회가 성공했으면 마지막 행을 그대로 보이고
# "expired"/auth_error 를 올리지 않는다 — 만료된 토큰은 여전히 보내지 않는다; (3) 120초가 지나도 키체인에
# 새 토큰이 없으면 행을 지우고 last_error "expired", auth_error True; (4) 60초 하한과 나머지 M1 규칙은 그대로.
#
# 해석 하나(보고서에 적음): 토큰은 만료 GEMINI_EXPIRY_MARGIN_SEC(60초) 전부터 '보내지 않는' 토큰이다. "agy 가
# 떠 있는 동안 상태가 한 번도 expired 가 아니다"를 지키려면 유예는 그 순간(만료 − 60초)부터 걸려야 한다.


class AgyLazyRefreshTests(_QuietCase):

    def test_agy_writing_the_new_token_just_after_expiry_never_blanks_the_pill(self):
        """agy 가 이전 토큰 만료 1·10·45초 뒤에 새 토큰을 쓰는 세 시간(30초 새로고침), 그 뒤 agy 를 닫는다.
          · agy 가 떠 있는 동안(마지막 토큰 만료 + 120초 전까지): 행이 한 번도 비지 않고, 상태가 한 번도
            "expired"·auth_error 가 아니며, 만료된 토큰을 보낸 적이 없다.
          · 키체인 읽기는 agy 가 떠 있는 동안 어느 한 시간 창에서도 8번 이하, 언제나 두 읽기 사이 ≥ 60초.
          · agy 를 닫으면 마지막 토큰 만료 뒤 180초 안에 "expired"(auth_error True)와 빈 행.
        Rivals: 8eb4ccb(만료 − 60초부터 바로 "expired", 만료된 토큰이면 300초마다만 다시 읽음 → 매시간
        1~2분 '만료'); 유예 없이 60초 하한만(만료 − 60초~새 토큰 사이 '만료'); 유예를 끝없이(agy 를 닫아도
        옛 숫자가 남음); 유예 중 만료된 토큰을 보내 봄(401 → auth_error)."""
        for lag in (1, 10, 45):
            with self.subTest(agy_writes_after_expiry=lag):
                self.restart_app()
                self.kc.reads.clear()
                self.server.requests.clear()
                base = self.clock.now = T0 + 1_000_000 * (lag + 1)
                period = 3600.0
                # 첫 만료를 750초에 둔다: 180초 캐시 주기의 조회(720초)가 '보낼 수 없는 구간'(만료 − 60초 ~
                # 새 토큰)에 떨어져야 유예 규칙이 실제로 시험된다. 600초로 두면 조회가 540초(딱 60초 남음,
                # 보낼 수 있음)와 720초(새 토큰 뒤)에만 일어나 그 구간을 건너뛰고, 유예 없는 구현이 통과한다
                # (scratch 로 확인).
                first_exp = base + 750
                open_end = base + 3 * 3600
                current = {"k": 0}
                self.issue("tok-%d-0" % lag, first_exp)

                def agy(now):
                    # agy 는 떠 있을 때만, 지금 토큰의 만료 lag 초 뒤에 다음 토큰을 쓴다.
                    k = current["k"]
                    exp_k = first_exp + period * k
                    if now < open_end and now >= exp_k + lag:
                        current["k"] = k + 1
                        self.issue("tok-%d-%d" % (lag, k + 1), first_exp + period * (k + 1))

                last_exp = first_exp + period * int((open_end - first_exp - lag) // period + 1)
                log = []
                while self.clock.time() <= last_exp + 600:
                    agy(self.clock.time())
                    rows = self.fetch()
                    st = self.status()
                    log.append((self.clock.time(), rows, st.get("last_error"), st.get("auth_error")))
                    self.clock.now += STEP
                self.assertEqual(current["k"], int((open_end - first_exp - lag) // period + 1),
                                 "하네스: agy 가 쓴 토큰 수가 예상과 다르다")
                running = [e for e in log if e[0] < last_exp + 120]
                blank = [e[0] - base for e in running if not e[1]]
                self.assertEqual(blank, [], "agy 가 떠 있는데 행이 빈 새로고침(기준 뒤 초): %r" % blank)
                bad = [(e[0] - base, e[2], e[3]) for e in running if e[2] == "expired" or e[3]]
                self.assertEqual(bad, [], "agy 가 떠 있는데 만료/거부 상태: %r" % bad[:6])
                for t, _ep, tok in self.server.requests:
                    self.assertGreater(self.server.expiry_of.get(tok, 0), t,
                                       "만료된 토큰을 보냈다(%s, 기준 뒤 %d초)" % (tok, t - base))
                reads = list(self.kc.reads)
                self.assertTrue(all(g >= 60 for g in _gaps(reads)), "읽기 간격 < 60초: %r" % _gaps(reads))
                # 시간당 상한은 agy 가 떠 있는 구간에만 건다. agy 를 닫은 뒤 마지막 만료 앞뒤(−300~+600초)는
                # 계약 (1)대로 60초 하한으로 읽으므로 그 구간만으로 15번까지 갈 수 있다 — 60초 하한이 그 상한이다.
                for start in range(int(base), int(last_exp - 300) - 3600 + 1, 300):
                    n = sum(1 for r in reads if start <= r < start + 3600)
                    self.assertLessEqual(n, 8, "한 시간 창(기준 뒤 %d~)에 읽기 %d번" % (start - base, n))
                closed = [e for e in log if e[0] >= last_exp]
                first = next((e for e in closed if e[2] == "expired"), None)
                self.assertIsNotNone(first, "agy 를 닫았는데 'expired' 가 끝내 안 나왔다")
                self.assertLessEqual(first[0] - last_exp, 180,
                                     "agy 를 닫은 뒤 'expired' 가 만료 %d초 뒤에야 나왔다" % (first[0] - last_exp))
                self.assertTrue(first[3], "만료인데 auth_error 가 내려가 있다")
                self.assertTrue(all(not e[1] for e in closed if e[0] >= first[0]),
                                "'expired' 뒤에도 옛 행이 남았다")


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

    def test_group_labels_follow_the_server_window_through_the_fetch_path(self):
        """리뷰 2차 R2-4: parse_gemini_quota 는 순수하다 — 그룹 window 표는 조회 경로(fetch)가 구간까지
        나른다. 그래서 끝에서 끝으로 본다: 새로고침 워커가 받은 state 를 앱의 `state["gemini_summary"]`
        훅(run_gui 에서 꺼낸 그 람다)에 넣으면 그룹 라벨이 서버의 window 를 따른다. bucketId 에는 window 가
        없다(q-1 = weekly, q-2 = 5h).
        Rivals: window 를 bucketId 에서 짐작(둘 다 "Claude·GPT"); 표가 구간에 닿지 않음; 파서가 모듈 표를
        채우는 8eb4ccb 방식은 이 테스트로는 통과하고 test_gemini_pill 의 순수성 게이트가 막는다."""
        self.server.summary = {"groups": [{"displayName": "Claude and GPT models", "buckets": [
            {"bucketId": "q-1", "window": "weekly", "resetTime": "2027-01-20T03:45:42Z",
             "remainingFraction": 0.9},
            {"bucketId": "q-2", "window": "5h", "resetTime": "2027-01-15T08:45:42Z",
             "remainingFraction": 0.1}]}]}
        claude_pet.RUNTIME["gemini_gauges"] = ["group"]
        state, _claude, _codex = self.drive(show_gemini=True)
        self.assertTrue(_wait(lambda: bool(state.get("gemini")), 5.0), "Gemini 행이 들어오지 않았다")
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        gui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_gui")
        hooks = [n.value for n in ast.walk(gui)
                 if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Subscript)
                 and isinstance(n.targets[0].slice, ast.Constant)
                 and n.targets[0].slice.value == "gemini_summary"]
        self.assertEqual(len(hooks), 1)
        scope = dict(vars(claude_pet), state=state)
        hook = eval(compile(ast.Expression(body=hooks[0]), str(SOURCE), "eval"), scope)
        lang = claude_pet.L.get("lang")
        self.addCleanup(lambda: claude_pet.L.__setitem__("lang", lang))
        claude_pet.L["lang"] = "en"
        seg = hook()
        self.assertIsNotNone(seg)
        tr = claude_pet.TR["en"]
        self.assertEqual([r[0] for r in seg[1]], [tr["gemini_group_weekly"], tr["gemini_group_5h"]])

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
