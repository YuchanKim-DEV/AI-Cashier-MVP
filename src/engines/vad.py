"""
VAD — 발화 구간(엔드포인팅) 검출. webrtcvad 기반.

Realtime API 의 server_vad 를 로컬에서 대체한다.
입력 오디오는 24kHz PCM16 (마이크). webrtcvad 는 24kHz 미지원(8/16/32/48k만)이라
16kHz 로 리샘플해서 30ms 프레임 단위로 판정한다.

상태 머신:
  침묵 중 speech 프레임 누적 → min_speech 넘으면 speech_start
  발화 중 silence 프레임 누적 → silence_ms 넘으면 speech_end
"""

import numpy as np
import webrtcvad

_FRAME_MS = 30
_VAD_RATE = 16000
_FRAME_BYTES = int(_VAD_RATE * _FRAME_MS / 1000) * 2   # 30ms @16k, 16bit = 960 bytes


def _resample_24k_to_16k_bytes(pcm16_24k: bytes) -> bytes:
    audio = np.frombuffer(pcm16_24k, dtype=np.int16).astype(np.float32)
    if audio.size == 0:
        return b""
    n_out = int(round(audio.size * 16000 / 24000))
    if n_out <= 0:
        return b""
    x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    out = np.interp(x_new, x_old, audio).astype(np.int16)
    return out.tobytes()


class UtteranceVAD:
    """24kHz PCM16 청크를 계속 밀어넣으면 speech_start/speech_end 이벤트를 돌려준다."""

    def __init__(self, aggressiveness: int = 2, silence_ms: int = 700, min_speech_ms: int = 200):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_frames_needed = max(1, silence_ms // _FRAME_MS)
        self.min_speech_frames = max(1, min_speech_ms // _FRAME_MS)
        self._buf16 = bytearray()      # 16k 프레임 정렬용 잔여 버퍼
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0

    def reset(self):
        self._buf16.clear()
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0

    def process(self, pcm16_24k: bytes) -> list[str]:
        """청크 처리 후 발생한 이벤트 목록 반환: 'speech_start' / 'speech_end'."""
        events: list[str] = []
        self._buf16.extend(_resample_24k_to_16k_bytes(pcm16_24k))
        while len(self._buf16) >= _FRAME_BYTES:
            frame = bytes(self._buf16[:_FRAME_BYTES])
            del self._buf16[:_FRAME_BYTES]
            try:
                is_speech = self.vad.is_speech(frame, _VAD_RATE)
            except Exception:
                is_speech = False
            if is_speech:
                self._speech_run += 1
                self._silence_run = 0
                if not self._in_speech and self._speech_run >= self.min_speech_frames:
                    self._in_speech = True
                    events.append("speech_start")
            else:
                self._silence_run += 1
                self._speech_run = 0
                if self._in_speech and self._silence_run >= self.silence_frames_needed:
                    self._in_speech = False
                    events.append("speech_end")
        return events

    @property
    def in_speech(self) -> bool:
        return self._in_speech


if __name__ == "__main__":
    # 무음 → 이벤트 없음 확인
    v = UtteranceVAD()
    silence = np.zeros(24000, dtype=np.int16).tobytes()
    print("무음 이벤트:", v.process(silence), "(비어야 정상)")
    # 랜덤 노이즈(발화 흉내) → speech_start 가능
    noise = (np.random.randn(24000) * 8000).astype(np.int16).tobytes()
    print("노이즈 이벤트:", v.process(noise))
