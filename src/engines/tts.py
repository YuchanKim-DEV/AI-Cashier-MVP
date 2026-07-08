"""
로컬 TTS — transformers VITS (facebook/mms-tts-*).

- 한국어: facebook/mms-tts-kor, 영어: facebook/mms-tts-eng
- 이미 설치된 torch 재사용 (별도 무거운 스택 없음)
- 출력 PCM16, 24kHz (파이프라인/브라우저와 통일). MMS 원본은 16kHz → 리샘플.

블로킹 추론이라 executor 에서 실행.
품질 업그레이드(MeloTTS 등)는 나중에 TTS_ENGINE 교체로 가능.
"""

import asyncio
import numpy as np

from src.engines import config

_MODEL_IDS = {
    "ko": "facebook/mms-tts-kor",
    "en": "facebook/mms-tts-eng",
}

_models: dict = {}      # lang -> (model, tokenizer, sample_rate)
_load_lock = asyncio.Lock()


def _resample_to_24k(wav: np.ndarray, src_rate: int) -> np.ndarray:
    """float32 [-1,1] → 24kHz float32."""
    if src_rate == config.TTS_SAMPLE_RATE or wav.size == 0:
        return wav
    n_out = int(round(wav.size * config.TTS_SAMPLE_RATE / src_rate))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, num=wav.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, wav).astype(np.float32)


def _load_sync(lang: str):
    from transformers import VitsModel, AutoTokenizer
    model_id = _MODEL_IDS.get(lang, _MODEL_IDS["ko"])
    print(f"[TTS] VITS 로딩: {model_id}")
    model = VitsModel.from_pretrained(model_id)
    tok = AutoTokenizer.from_pretrained(model_id)
    model.eval()
    sr = int(model.config.sampling_rate)
    print(f"[TTS] 로딩 완료: {model_id} (sr={sr})")
    return model, tok, sr


async def preload(lang: str = "ko"):
    async with _load_lock:
        if lang not in _models:
            _models[lang] = await asyncio.get_event_loop().run_in_executor(None, _load_sync, lang)


def _synth_sync(lang: str, text: str) -> bytes:
    import torch
    model, tok, sr = _models[lang]
    inputs = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs).waveform    # [1, T] float32
    wav = out.squeeze().cpu().numpy().astype(np.float32)
    # 속도 조절 (config.TTS_SPEED): 1.0 이면 그대로 (브라우저가 1.35배속 재생)
    if abs(config.TTS_SPEED - 1.0) > 1e-3 and wav.size > 0:
        n_out = int(round(wav.size / config.TTS_SPEED))
        if n_out > 0:
            x_old = np.linspace(0, 1, wav.size, endpoint=False)
            x_new = np.linspace(0, 1, n_out, endpoint=False)
            wav = np.interp(x_new, x_old, wav).astype(np.float32)
    wav = _resample_to_24k(wav, sr)
    # float32 → PCM16
    wav = np.clip(wav, -1.0, 1.0)
    pcm16 = (wav * 32767.0).astype(np.int16)
    return pcm16.tobytes()


async def synthesize(text: str, lang: str = "ko") -> bytes:
    """텍스트 → PCM16 24kHz bytes. 실패/빈 텍스트면 b''."""
    text = (text or "").strip()
    if not text:
        return b""
    lang = "en" if lang == "en" else "ko"
    if lang not in _models:
        await preload(lang)
    try:
        return await asyncio.get_event_loop().run_in_executor(None, _synth_sync, lang, text)
    except Exception as e:
        print(f"[TTS] 합성 오류: {e}")
        return b""


# ─── 단독 테스트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, wave

    async def _main():
        text = sys.argv[1] if len(sys.argv) > 1 else "어서오세요! 뭐 드릴까요?"
        await preload("ko")
        pcm = await synthesize(text, "ko")
        print(f"합성 결과: {len(pcm)} bytes ({len(pcm)/2/24000:.2f}s @24k)")
        out = "/private/tmp/claude-501/-Users-yuchan-Desktop-mvp-ai-Cashier/3bd3ff1d-a853-417a-8ae9-afbed2ff93a3/scratchpad/tts_test.wav"
        with wave.open(out, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(pcm)
        print(f"저장: {out}")

    asyncio.run(_main())
