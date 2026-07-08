"""
엔진 설정 — 로컬/클라우드 스위치 및 모델 선택.

ENGINE_MODE 로 전체 음성 파이프라인(STT+LLM+TTS)을 한 번에 전환한다.
  - "local": faster-whisper + Ollama + 로컬 TTS (API 비용 0)
  - "cloud": 기존 OpenAI Realtime API (백업 — 코드 그대로 보존)

각 모델명은 env 로 교체 가능 → 지금은 작은 모델(M1 8GB), 나중에 클라우드/GPU 에선
큰 모델명만 env 로 바꾸면 코드 변경 없이 확장된다.
"""

import os


def engine_mode() -> str:
    """'local' | 'cloud'. 기본값은 local (비용 0)."""
    mode = os.getenv("ENGINE_MODE", "local").strip().lower()
    return "cloud" if mode == "cloud" else "local"


def is_local() -> bool:
    return engine_mode() == "local"


# ─── STT (faster-whisper) ────────────────────────────────────────────────────
# 모델: tiny / base / small / medium / large-v3
#   M1 8GB 권장: small (한국어 OK, ~1GB, int8)
#   클라우드/GPU: large-v3
STT_MODEL       = os.getenv("STT_MODEL", "small")
STT_DEVICE      = os.getenv("STT_DEVICE", "cpu")        # cpu | cuda
STT_COMPUTE     = os.getenv("STT_COMPUTE", "int8")      # int8 | int8_float16 | float16
STT_LANGUAGE    = os.getenv("STT_LANGUAGE", "")         # "" = 자동감지, "ko"/"en" 강제 가능


# ─── LLM (Ollama, OpenAI 호환 API) ───────────────────────────────────────────
#   M1 8GB 권장: qwen2.5:3b-instruct-q4_K_M
#   클라우드/GPU: qwen2.5:14b / 32b
LLM_BASE_URL    = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY     = os.getenv("LLM_API_KEY", "ollama")    # Ollama 는 아무 값이나 허용
LLM_MODEL       = os.getenv("LLM_MODEL", "qwen2.5:3b")   # instruct q4_K_M (~1.9GB)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))   # 낮게 → 할루시네이션 억제
LLM_MAX_TOKENS  = int(os.getenv("LLM_MAX_TOKENS", "160"))       # 장황함/할루시네이션 억제 (짧게 강제)


# ─── TTS (로컬) ──────────────────────────────────────────────────────────────
#   TTS_ENGINE: "melo" | "kokoro" | "piper"  (설치된 것에 맞춰 선택)
TTS_ENGINE      = os.getenv("TTS_ENGINE", "melo")
TTS_SPEED       = float(os.getenv("TTS_SPEED", "1.0"))   # 브라우저가 1.35배속 재생 → 여기선 1.0
TTS_SAMPLE_RATE = 24000   # 프론트/스피커와 맞춤 (RealtimeClient 와 동일)


# ─── 공통 오디오 ─────────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 24000   # 마이크/스피커 PCM16 24kHz
