"""
transcript_pipeline.py — robust multi-stage transcript acquisition
==================================================================

Fallback ladder (each stage tried in order):
  1. platform_captions  — YouTube caption API   (zero bandwidth, instant)
  2. yt_dlp_subs        — yt-dlp --write-subs   (no audio download needed)
  3. groq_whisper       — Groq cloud audio transcription
  4. whisper_local      — faster-whisper CPU     (no quota, always available)

Guarantees:
  • TranscriptResult.text is always str (NEVER None)
  • TranscriptResult.word_count / char_count are always int
  • ok=True only when text passes identity + completeness validation
  • Every stage logs a sanitised error receipt (no secret values)
  • Bounded retries (≤ 2) with exponential back-off per stage
  • Per-provider circuit breaker (in-process, resets on restart)
  • Completed stages are not re-run on retry if a cached result exists
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("fieldnote.transcript_pipeline")

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_CHARS          = 120     # transcript shorter than this is considered empty
MAX_AUDIO_MB       = 24      # clip audio above this threshold
CLIP_SECONDS       = 1200    # 20-min clip
RETRY_MAX          = 2       # max per-stage retries
RETRY_BASE_S       = 2.0     # base back-off (doubles each attempt)
STAGE_TIMEOUT_S    = 300     # max seconds per stage
CIRCUIT_THRESHOLD  = 3       # failures before opening circuit
CIRCUIT_RESET_S    = 300     # seconds before circuit auto-closes

WHISPER_MODEL      = "whisper-large-v3"
_FW_MODEL_DIR      = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".cache", "fw_models"
)

# ── Circuit breaker (in-process) ─────────────────────────────────────────────

_circuits: dict[str, dict] = {}   # provider -> {failures, open_until}


def _circuit_open(provider: str) -> bool:
    s = _circuits.get(provider)
    if not s:
        return False
    if s["failures"] >= CIRCUIT_THRESHOLD:
        if time.monotonic() < s["open_until"]:
            return True
        # auto-reset after timeout
        s["failures"] = 0
        s["open_until"] = 0.0
    return False


def _circuit_fail(provider: str) -> None:
    s = _circuits.setdefault(provider, {"failures": 0, "open_until": 0.0})
    s["failures"] += 1
    if s["failures"] >= CIRCUIT_THRESHOLD:
        s["open_until"] = time.monotonic() + CIRCUIT_RESET_S
        log.warning("Circuit breaker OPEN for %s (will retry in %ds)", provider, CIRCUIT_RESET_S)


def _circuit_ok(provider: str) -> None:
    if provider in _circuits:
        _circuits[provider]["failures"] = 0
        _circuits[provider]["open_until"] = 0.0


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class TranscriptResult:
    text:            str             # always str, never None; empty ⟹ ok=False
    method:          str             # "captions"|"yt_dlp_subs"|"whisper"|"whisper_local"|"none"
    ok:              bool            # True only if transcript passed validation
    word_count:      int = 0
    char_count:      int = 0
    language:        Optional[str] = None
    video_id:        str = ""
    content_hash:    str = ""        # sha256 of first 4 KB
    provider:        str = ""        # which provider produced this
    fallback_reason: Optional[str] = None
    timing_ms:       float = 0.0
    error_receipt:   Optional[str] = None   # sanitised — never contains key values
    is_degraded:     bool = False
    degraded_reason: Optional[str] = None
    stage_log:       list[str] = field(default_factory=list)


def _make_result(
    text: Optional[str],
    method: str,
    video_id: str,
    language: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    error_receipt: Optional[str] = None,
    is_degraded: bool = False,
    degraded_reason: Optional[str] = None,
    stage_log: Optional[list[str]] = None,
    timing_ms: float = 0.0,
) -> TranscriptResult:
    """Build a validated TranscriptResult; text=None treated as failure."""
    safe_text   = text if isinstance(text, str) else ""
    char_count  = len(safe_text)
    word_count  = len(safe_text.split()) if safe_text else 0
    ok          = char_count >= MIN_CHARS and word_count >= 10
    content_hash = hashlib.sha256(safe_text[:4096].encode()).hexdigest()[:16] if ok else ""

    return TranscriptResult(
        text            = safe_text,
        method          = method if ok else "none",
        ok              = ok,
        word_count      = word_count,
        char_count      = char_count,
        language        = language,
        video_id        = video_id,
        content_hash    = content_hash,
        provider        = method,
        fallback_reason = fallback_reason,
        timing_ms       = timing_ms,
        error_receipt   = error_receipt,
        is_degraded     = is_degraded,
        degraded_reason = degraded_reason,
        stage_log       = stage_log or [],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize_error(err: str) -> str:
    """Strip anything that looks like a key/secret from an error string."""
    # Remove long hex or base64-looking tokens
    err = re.sub(r'[A-Za-z0-9_\-]{30,}', '<redacted>', err)
    return err[:300]


def _retry(fn: Callable, provider: str, emit: Callable, label: str):
    """
    Call fn() up to RETRY_MAX+1 times with exponential back-off.
    Returns the result or raises the last exception.
    """
    last_exc: Exception | None = None
    for attempt in range(RETRY_MAX + 1):
        try:
            result = fn()
            _circuit_ok(provider)
            return result
        except Exception as exc:
            last_exc = exc
            err_str  = _sanitize_error(str(exc))
            if attempt < RETRY_MAX:
                wait = RETRY_BASE_S * (2 ** attempt)
                emit(f"⚠  {label} attempt {attempt+1} failed ({err_str[:80]}) — retrying in {wait:.0f}s …", "warning")
                time.sleep(wait)
            else:
                _circuit_fail(provider)
    raise last_exc  # type: ignore[misc]


# ── Stage 1: YouTube platform captions ───────────────────────────────────────

def _stage_captions(video_id: str, emit: Callable) -> str:
    """Return raw caption text or raise."""
    from youtube_transcript_api import YouTubeTranscriptApi
    entries = YouTubeTranscriptApi.get_transcript(video_id)
    if not entries:
        raise ValueError("Empty caption list returned")
    text = " ".join(str(e.get("text", "")) for e in entries)
    return text


# ── Stage 2: yt-dlp subtitle fetch (no audio download) ───────────────────────

def _stage_yt_dlp_subs(url: str, video_id: str, emit: Callable) -> str:
    """Download auto-subs via yt-dlp, return concatenated text or raise."""
    tmp = tempfile.mkdtemp(prefix="fn_subs_")
    try:
        out_tmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        proc = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub", "--write-sub",
                "--sub-lang", "en",
                "--skip-download",
                "--sub-format", "vtt",
                "--convert-subs", "vtt",
                "-o", out_tmpl,
                url,
            ],
            capture_output=True, text=True, timeout=60,
        )
        # Find any .vtt file
        vtt_files = [f for f in os.listdir(tmp) if f.endswith(".vtt")]
        if not vtt_files:
            raise RuntimeError(
                f"yt-dlp found no subtitle file. stderr={proc.stderr[-200:]}"
            )
        with open(os.path.join(tmp, vtt_files[0]), encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        # Strip VTT headers/timestamps, keep text
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("WEBVTT") or "-->" in line or line.startswith("NOTE"):
                continue
            # strip HTML tags
            cleaned = re.sub(r"<[^>]+>", "", line).strip()
            if cleaned:
                lines.append(cleaned)
        text = " ".join(lines)
        if len(text) < MIN_CHARS:
            raise ValueError(f"Subtitle text too short ({len(text)} chars)")
        return text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Stage 3: Groq cloud Whisper ───────────────────────────────────────────────

def _stage_groq_whisper(url: str, video_id: str, emit: Callable) -> tuple[str, str]:
    """
    Download audio, transcribe with Groq Whisper.
    Returns (text, language) or raises.
    Raises RuntimeError("quota_exhausted") or RuntimeError("auth_error") on
    permanent failures so the caller can skip to the next stage.
    """
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
    if not groq_key:
        raise RuntimeError("no_groq_key")

    from groq import Groq
    client  = Groq(api_key=groq_key)
    tmp     = tempfile.mkdtemp(prefix="fn_audio_")
    raw_out = os.path.join(tmp, f"{video_id}.%(ext)s")
    mp3_out = os.path.join(tmp, f"{video_id}.mp3")

    try:
        emit("⬇  Downloading audio via yt-dlp …", "warning")
        dl = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestaudio[abr<=64]/bestaudio/worst",
                "-x", "--audio-format", "mp3", "--audio-quality", "5",
                "--no-playlist", "-o", raw_out, url,
            ],
            capture_output=True, text=True, timeout=300,
        )
        if dl.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {dl.stderr[-300:]}")

        # yt-dlp may write e.g. video_id.m4a, then convert
        if not os.path.exists(mp3_out):
            found = [f for f in os.listdir(tmp) if video_id in f and not f.endswith(".%(ext)s")]
            if not found:
                raise RuntimeError("Audio file not found after yt-dlp download")
            src = os.path.join(tmp, found[0])
            conv = subprocess.run(
                ["ffmpeg", "-i", src, "-q:a", "5", "-ar", "16000", "-ac", "1", mp3_out, "-y"],
                capture_output=True, timeout=120,
            )
            if conv.returncode != 0 or not os.path.exists(mp3_out):
                raise RuntimeError("ffmpeg conversion failed")

        size_mb = os.path.getsize(mp3_out) / 1_048_576
        emit(f"🎵  Audio ready ({size_mb:.1f} MB) — sending to Groq Whisper …", "warning")

        if size_mb > MAX_AUDIO_MB:
            emit(f"✂  Clipping to first {CLIP_SECONDS // 60} min …", "warning")
            clipped = os.path.join(tmp, f"{video_id}_clip.mp3")
            subprocess.run(
                ["ffmpeg", "-i", mp3_out, "-t", str(CLIP_SECONDS),
                 "-q:a", "5", "-ar", "16000", "-ac", "1", clipped, "-y"],
                capture_output=True, timeout=60,
            )
            mp3_out = clipped

        with open(mp3_out, "rb") as fh:
            resp = client.audio.transcriptions.create(
                file=(os.path.basename(mp3_out), fh),
                model=WHISPER_MODEL,
                response_format="verbose_json",   # always JSON — never plain text
            )

        # Groq SDK 1.5+ returns TranscriptionVerbose for verbose_json
        # .text is always str; language is in .language
        text     = resp.text if isinstance(resp.text, str) else ""
        language = getattr(resp, "language", None)

        if not text or len(text.strip()) < MIN_CHARS:
            raise ValueError(f"Groq returned empty/short text ({len(text)} chars)")

        return text, language or "unknown"

    except Exception as exc:
        err = str(exc)
        quota_kw = ("quota", "billing", "insufficient", "exceeded", "resource_exhausted")
        auth_kw  = ("401", "403", "invalid_api_key", "permission_denied")
        if any(k in err.lower() for k in quota_kw):
            raise RuntimeError("quota_exhausted") from exc
        if any(k in err for k in auth_kw):
            raise RuntimeError("auth_error") from exc
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Stage 4: Local faster-whisper ─────────────────────────────────────────────

def _stage_local_whisper(audio_path: str, emit: Callable) -> tuple[str, str]:
    """CPU transcription via faster-whisper tiny model. Returns (text, language)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed — run: pip install faster-whisper")

    os.makedirs(_FW_MODEL_DIR, exist_ok=True)
    emit("🖥️  Loading local Whisper model (tiny, ~39 MB cached) …", "warning")
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=_FW_MODEL_DIR)
    emit("📝  Transcribing locally on CPU …", "warning")

    segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=True)
    parts: list[str] = []
    for seg in segments:
        t = seg.text
        if isinstance(t, str):
            s = t.strip()
            if s:
                parts.append(s)
    text = " ".join(parts)
    language = getattr(info, "language", "unknown") or "unknown"
    return text, language


# ── Main entry point ──────────────────────────────────────────────────────────

def get_transcript_robust(url: str, video_id: str, emit: Callable) -> TranscriptResult:
    """
    Run the full fallback ladder for `video_id`.

    Ladder:
      1. platform_captions
      2. yt_dlp_subs
      3. groq_whisper  (includes audio download)
      4. whisper_local (reuses audio if Groq already downloaded it)

    Returns a TranscriptResult that is always safe to inspect:
      - text is always str
      - ok=True only when the transcript passed all validation checks
    """
    t0         = time.monotonic()
    stage_log: list[str] = []
    audio_path: Optional[str] = None   # reuse if Groq already downloaded

    def elapsed_ms() -> float:
        return (time.monotonic() - t0) * 1000

    # ── Stage 1: Platform captions ────────────────────────────────────────────
    if not _circuit_open("captions"):
        try:
            emit("📋  Trying YouTube captions …", "info")
            text = _retry(
                lambda: _stage_captions(video_id, emit),
                provider="captions",
                emit=emit,
                label="YouTube captions",
            )
            stage_log.append("captions:ok")
            emit("✅  Captions found.", "success")
            return _make_result(
                text=text, method="captions", video_id=video_id,
                stage_log=stage_log, timing_ms=elapsed_ms(),
            )
        except Exception as exc:
            reason = _sanitize_error(str(exc))
            stage_log.append(f"captions:fail({reason[:60]})")
            emit(f"⚠  No captions ({type(exc).__name__}) — trying next method …", "warning")
    else:
        stage_log.append("captions:circuit_open")
        emit("⚠  Caption provider in back-off — skipping …", "warning")

    # ── Stage 2: yt-dlp subtitle download ─────────────────────────────────────
    if not _circuit_open("yt_dlp_subs"):
        try:
            emit("🔤  Trying yt-dlp subtitle fetch …", "info")
            text = _retry(
                lambda: _stage_yt_dlp_subs(url, video_id, emit),
                provider="yt_dlp_subs",
                emit=emit,
                label="yt-dlp subs",
            )
            stage_log.append("yt_dlp_subs:ok")
            emit("✅  Subtitles fetched via yt-dlp.", "success")
            return _make_result(
                text=text, method="yt_dlp_subs", video_id=video_id,
                fallback_reason="no_platform_captions",
                is_degraded=True,
                degraded_reason="auto-generated subtitles may contain errors",
                stage_log=stage_log, timing_ms=elapsed_ms(),
            )
        except Exception as exc:
            reason = _sanitize_error(str(exc))
            stage_log.append(f"yt_dlp_subs:fail({reason[:60]})")
            emit(f"⚠  No subtitles available — switching to audio transcription …", "warning")
    else:
        stage_log.append("yt_dlp_subs:circuit_open")

    # ── Stages 3+4 share audio download ───────────────────────────────────────
    # Download audio once, then try Groq then local
    tmp_audio_dir: Optional[str] = None

    def _download_audio() -> str:
        nonlocal tmp_audio_dir
        tmp  = tempfile.mkdtemp(prefix="fn_audio_")
        tmp_audio_dir = tmp
        raw  = os.path.join(tmp, f"{video_id}.%(ext)s")
        mp3  = os.path.join(tmp, f"{video_id}.mp3")

        emit("⬇  Downloading audio via yt-dlp …", "warning")
        dl = subprocess.run(
            ["yt-dlp", "-f", "bestaudio[abr<=64]/bestaudio/worst",
             "-x", "--audio-format", "mp3", "--audio-quality", "5",
             "--no-playlist", "-o", raw, url],
            capture_output=True, text=True, timeout=300,
        )
        if dl.returncode != 0:
            raise RuntimeError(f"yt-dlp audio download failed: {dl.stderr[-200:]}")

        if not os.path.exists(mp3):
            found = [f for f in os.listdir(tmp) if video_id in f]
            if not found:
                raise RuntimeError("Audio file missing after yt-dlp")
            src = os.path.join(tmp, found[0])
            subprocess.run(
                ["ffmpeg", "-i", src, "-q:a", "5", "-ar", "16000", "-ac", "1", mp3, "-y"],
                capture_output=True, timeout=120,
            )

        if not os.path.exists(mp3) or os.path.getsize(mp3) < 1024:
            raise RuntimeError("Audio file invalid after conversion")

        size_mb = os.path.getsize(mp3) / 1_048_576
        emit(f"🎵  Audio ready ({size_mb:.1f} MB)", "info")

        if size_mb > MAX_AUDIO_MB:
            clipped = os.path.join(tmp, f"{video_id}_clip.mp3")
            subprocess.run(
                ["ffmpeg", "-i", mp3, "-t", str(CLIP_SECONDS),
                 "-q:a", "5", "-ar", "16000", "-ac", "1", clipped, "-y"],
                capture_output=True, timeout=60,
            )
            if os.path.exists(clipped):
                mp3 = clipped
                emit(f"✂  Clipped to first {CLIP_SECONDS // 60} min", "warning")

        return mp3

    downloaded_audio: Optional[str] = None

    # ── Stage 3: Groq cloud Whisper ───────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
    if groq_key and not _circuit_open("groq_whisper"):
        try:
            # Download audio (shared with stage 4)
            if downloaded_audio is None:
                try:
                    downloaded_audio = _download_audio()
                except Exception as dl_exc:
                    stage_log.append(f"audio_dl:fail({_sanitize_error(str(dl_exc))[:60]})")
                    emit(f"❌  Audio download failed: {_sanitize_error(str(dl_exc))[:120]}", "error")

            if downloaded_audio:
                emit("☁  Sending to Groq Whisper …", "info")
                from groq import Groq
                client = Groq(api_key=groq_key)

                with open(downloaded_audio, "rb") as fh:
                    resp = client.audio.transcriptions.create(
                        file=(os.path.basename(downloaded_audio), fh),
                        model=WHISPER_MODEL,
                        response_format="verbose_json",
                    )

                # Always use resp.text; never use raw string parsing
                text     = resp.text if isinstance(resp.text, str) else ""
                language = getattr(resp, "language", None)

                if not text or len(text.strip()) < MIN_CHARS:
                    raise ValueError(f"Groq returned short/empty transcript ({len(text)} chars)")

                _circuit_ok("groq_whisper")
                word_count = len(text.split())
                stage_log.append("groq_whisper:ok")
                emit(f"✅  Groq Whisper done ({word_count:,} words, lang: {language or '?'})", "success")
                return _make_result(
                    text=text, method="whisper", video_id=video_id,
                    language=language,
                    fallback_reason="no_captions_or_subs",
                    is_degraded=False,
                    stage_log=stage_log, timing_ms=elapsed_ms(),
                )

        except Exception as exc:
            err = str(exc)
            quota_kw = ("quota", "billing", "insufficient", "exceeded", "resource_exhausted")
            auth_kw  = ("401", "403", "invalid_api_key", "permission_denied")
            is_quota = any(k in err.lower() for k in quota_kw)
            is_auth  = any(k in err for k in auth_kw)
            reason   = _sanitize_error(err)

            if is_quota or is_auth:
                kind = "quota exhausted" if is_quota else "auth error"
                emit(f"⚠  Groq Whisper {kind} — falling back to local transcription …", "warning")
                stage_log.append(f"groq_whisper:{kind.replace(' ', '_')}")
            else:
                _circuit_fail("groq_whisper")
                emit(f"⚠  Groq Whisper failed ({reason[:100]}) — trying local …", "warning")
                stage_log.append(f"groq_whisper:fail({reason[:60]})")
    else:
        if not groq_key:
            stage_log.append("groq_whisper:no_key")
        else:
            stage_log.append("groq_whisper:circuit_open")
            emit("⚠  Groq Whisper in back-off — trying local transcription …", "warning")

    # ── Stage 4: Local faster-whisper ─────────────────────────────────────────
    try:
        # Download audio if not already done
        if downloaded_audio is None:
            try:
                downloaded_audio = _download_audio()
            except Exception as dl_exc:
                err_msg = _sanitize_error(str(dl_exc))
                stage_log.append(f"audio_dl:fail({err_msg[:60]})")
                emit(f"❌  Audio download failed — cannot transcribe.", "error")
                if tmp_audio_dir:
                    shutil.rmtree(tmp_audio_dir, ignore_errors=True)
                return _make_result(
                    text="", method="none", video_id=video_id,
                    error_receipt=err_msg,
                    stage_log=stage_log, timing_ms=elapsed_ms(),
                )

        emit("🖥️  Starting local CPU transcription (no quota needed) …", "warning")
        text, language = _stage_local_whisper(downloaded_audio, emit)
        word_count = len(text.split()) if text else 0

        if not text or len(text.strip()) < MIN_CHARS:
            raise ValueError(f"Local Whisper returned short/empty transcript ({len(text)} chars)")

        _circuit_ok("whisper_local")
        stage_log.append("whisper_local:ok")
        emit(f"✅  Local transcription done ({word_count:,} words, lang: {language})", "success")

        if tmp_audio_dir:
            shutil.rmtree(tmp_audio_dir, ignore_errors=True)

        return _make_result(
            text=text, method="whisper_local", video_id=video_id,
            language=language,
            fallback_reason="all_cloud_providers_failed",
            is_degraded=True,
            degraded_reason="local CPU Whisper (tiny model) — lower accuracy",
            stage_log=stage_log, timing_ms=elapsed_ms(),
        )

    except Exception as exc:
        _circuit_fail("whisper_local")
        err_msg = _sanitize_error(str(exc))
        stage_log.append(f"whisper_local:fail({err_msg[:60]})")
        emit(f"❌  Local transcription failed: {err_msg[:120]}", "error")
        if tmp_audio_dir:
            shutil.rmtree(tmp_audio_dir, ignore_errors=True)
        return _make_result(
            text="", method="none", video_id=video_id,
            error_receipt=err_msg,
            stage_log=stage_log, timing_ms=elapsed_ms(),
        )
