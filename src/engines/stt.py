"""
로컬 STT — faster-whisper (CTranslate2).

입력: PCM16 mono, 24kHz (마이크 캡처와 동일)
출력: 전사 텍스트 + 감지 언어

faster-whisper 는 16kHz float32 를 기대하므로 내부에서 24kHz→16kHz 리샘플 한다.
블로킹 추론이라 asyncio executor 에서 돌린다.
"""

import asyncio
import numpy as np

from src.engines import config

_model = None
_load_lock = asyncio.Lock()


def _resample_24k_to_16k(pcm16: bytes) -> np.ndarray:
    """PCM16 24kHz bytes → float32 16kHz numpy (whisper 입력용, -1~1 정규화)."""
    audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size == 0:
        return audio
    # 24000 → 16000 (비율 2/3) 선형 보간 리샘플
    n_out = int(round(audio.size * 16000 / 24000))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _load_model_sync():
    from faster_whisper import WhisperModel
    print(f"[STT] faster-whisper 로딩: model={config.STT_MODEL} "
          f"device={config.STT_DEVICE} compute={config.STT_COMPUTE}")
    m = WhisperModel(
        config.STT_MODEL,
        device=config.STT_DEVICE,
        compute_type=config.STT_COMPUTE,
    )
    print("[STT] 로딩 완료")
    return m


async def preload():
    """모델 미리 로딩 (첫 발화 지연 방지)."""
    global _model
    async with _load_lock:
        if _model is None:
            _model = await asyncio.get_event_loop().run_in_executor(None, _load_model_sync)


def _transcribe_sync(audio16k: np.ndarray, language: str | None, initial_prompt: str | None) -> tuple[str, str]:
    segments, info = _model.transcribe(
        audio16k,
        language=language or None,
        beam_size=1,                 # MVP: 속도 우선 (greedy)
        vad_filter=True,             # 무음 구간 제거 → 할루시네이션 억제
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,   # 이전 텍스트 반복 할루시네이션 방지
        no_speech_threshold=0.6,
        initial_prompt=initial_prompt,      # 메뉴 어휘 힌트 → 도메인 단어 오인식 감소
    )
    text = "".join(seg.text for seg in segments).strip()
    return text, info.language


async def transcribe(pcm16: bytes, sample_rate: int = 24000,
                     initial_prompt: str | None = None) -> tuple[str, str]:
    """
    PCM16 → (텍스트, 감지언어). 실패/무음이면 ("", "").
    initial_prompt: 메뉴명 등 도메인 어휘 힌트 (오인식 감소).
    sample_rate 는 24000 고정 가정 (다르면 향후 확장).
    """
    if _model is None:
        await preload()
    audio16k = _resample_24k_to_16k(pcm16)
    if audio16k.size < 1600:   # 0.1초 미만 → 무시
        return "", ""
    lang = config.STT_LANGUAGE or None
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _transcribe_sync, audio16k, lang, initial_prompt
        )
    except Exception as e:
        print(f"[STT] 전사 오류: {e}")
        return "", ""


# ─── 단독 테스트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    async def _main():
        await preload()
        if len(sys.argv) > 1:
            # 파일 경로 인자 → 파일 전사 (16k float 로 자동 처리는 아래 별도)
            import wave
            with wave.open(sys.argv[1], "rb") as w:
                sr = w.getframerate()
                raw = w.readframes(w.getnframes())
            print(f"입력: {sys.argv[1]} sr={sr} bytes={len(raw)}")
            # 파일이 24k 가정; 아니면 sr 로 리샘플 필요
            text, lang = await transcribe(raw, sample_rate=sr)
            print(f"전사: {text!r} (lang={lang})")
        else:
            # 사인파 무음 테스트 (모델 로딩/추론 경로만 확인)
            silence = (np.zeros(24000, dtype=np.int16)).tobytes()
            text, lang = await transcribe(silence)
            print(f"무음 전사 결과: {text!r} (lang={lang}) — 로딩/추론 경로 정상")

    asyncio.run(_main())
