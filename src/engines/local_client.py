"""
LocalVoiceClient — 완전 로컬 음성 파이프라인.

RealtimeClient(OpenAI Realtime API)와 **동일한 콜백/메서드 인터페이스**를 제공해서
main.py 오케스트레이터가 그대로 스왑할 수 있다 (ENGINE_MODE=local).

파이프라인 (Realtime 의 speech-to-speech 단일 스트림을 로컬에서 분리):
    마이크 PCM(24k) → VAD(발화구간) → STT(faster-whisper)
        → LLM(Ollama qwen2.5, tool calling) → TTS(VITS) → 스피커

할루시네이션 억제:
  - 시스템 프롬프트에 실제 메뉴/가격을 그대로 grounding
  - temperature 낮춤 (config)
  - 툴 인자는 handlers/cart 에서 실제 메뉴 대조 검증 (기존 로직 재사용)
"""

import asyncio
import base64
import json
import time
import uuid
from typing import Callable, Optional, Awaitable

from src.engines import config, stt, tts
from src.engines.llm import LocalLLM, to_chat_tools
from src.engines.vad import UtteranceVAD
from src.tools.handlers import TOOLS
from src.tools.menu import MENU_DATA


def _menu_text() -> str:
    """실제 메뉴를 프롬프트에 넣을 문자열로 (할루시네이션 방지 grounding)."""
    lines = []
    for cat, items in MENU_DATA.items():
        parts = [f"{it['name']}({it['price']}원)" for it in items]
        lines.append(f"[{cat}] " + ", ".join(parts))
    return "\n".join(lines)


def _stt_hint() -> str:
    """STT 힌트 — 메뉴명 등 도메인 어휘로 오인식(예: 치즈버거→지즈버거) 감소."""
    names = [it["name"] for items in MENU_DATA.values() for it in items]
    return ("햄버거 가게 주문: " + ", ".join(names)
            + ", 세트, 결제할게요, 추천해주세요, 빼주세요, 장바구니, 앱카드, 현장카드, 주세요.")


def _system_prompt(lang: str, user_name: Optional[str], is_new_user: bool,
                   preferences: Optional[str] = None) -> str:
    menu = _menu_text()
    if lang == "en":
        p = (
            "You are 'Kay', a warm, upbeat AI cashier at a burger restaurant (O2O Burger). "
            "Talk like a real, friendly service employee. Respond ONLY in English, 1-2 short sentences.\n"
            f"MENU (only these items exist — never invent items or prices):\n{menu}\n"
            "Rules:\n"
            "- When the customer names a menu item, immediately call add_to_cart with the EXACT menu name.\n"
            "- If they ask to remove something, call remove_from_cart.\n"
            "- Call recommend_menu only when they ask for suggestions.\n"
            "- Call checkout when the order is done (never if the cart is empty).\n"
            "- On the payment screen, call select_payment when they mention app card or physical card.\n"
            "- If a request is not on the menu, say so honestly. Do NOT make things up.\n"
            "- NEVER mention discounts, freebies, or events — none exist.\n"
            "- Do not repeat greetings."
        )
        if is_new_user and not user_name:
            p += "\n- Once, near checkout, mention they can register name+phone in the app for voice ordering next time."
        if user_name:
            p += f"\n- This customer is {user_name}. Greet them warmly by name once."
        if preferences:
            p += f"\n- Past preference of this customer: {preferences}. Use it for recommendations when relevant."
    else:
        p = (
            "너는 햄버거 가게(오투오버거) 카운터 직원 '케이'야. 진짜 서비스직 직원처럼 밝고 친절하게, "
            "존댓말로 1~2문장 짧게 한국어로만 말해.\n"
            f"메뉴 (아래 항목만 존재 — 없는 메뉴/가격을 절대 지어내지 마):\n{menu}\n"
            "규칙:\n"
            "- 손님이 메뉴 이름을 말하면 즉시 add_to_cart 를 정확한 메뉴명으로 호출해.\n"
            "- 구어체도 메뉴명으로 변환해 호출: 감튀→감자튀김, 콜라 종류→콜라, 불고기→불고기버거.\n"
            "- 취소하면 remove_from_cart 호출.\n"
            "- 추천은 손님이 물어볼 때만 recommend_menu 호출.\n"
            "- 주문이 끝나면 checkout 호출 (장바구니 비었으면 절대 금지).\n"
            "- 결제 화면에서 앱카드/현장카드 말하면 select_payment 호출.\n"
            "- 메뉴에 없는 요청은 솔직히 없다고 말해. 절대 지어내지 마.\n"
            "- 할인/무료/이벤트는 존재하지 않아. 절대 언급 금지.\n"
            "- 인사말 반복 금지.\n"
            "예시:\n"
            "  손님 '치즈버거 하나랑 감튀요' → add_to_cart(치즈버거), add_to_cart(감자튀김) → '네! 치즈버거랑 감자튀김 담아드렸어요~'\n"
            "  손님 '이제 됐어요, 계산할게요' → checkout() → '결제 화면으로 안내드릴게요!'\n"
            "  손님 '아메리카노 있어요?' → (툴 호출 없이) '앗, 저희는 커피는 없어요! 콜라나 아이스티는 어떠세요?'"
        )
        if is_new_user and not user_name:
            p += "\n- 결제 즈음 한 번만: '이름이랑 번호 등록하시면 다음엔 목소리로 바로 주문 가능해요, 앱에서 등록되세요~' 라고 안내."
        if user_name:
            p += f"\n- 이 손님은 '{user_name}'님이야. 처음 한 번만 이름 불러 반갑게 맞이해."
        if preferences:
            p += f"\n- 이 손님의 지난 취향: {preferences}. 추천할 때 자연스럽게 활용해 (강요 금지)."
    return p


class LocalVoiceClient:
    def __init__(
        self,
        api_key: str = "",            # 로컬은 미사용 (인터페이스 호환용)
        model: str = "",
        voice: str = "",
        on_audio_delta: Optional[Callable[[str], None]] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_ai_transcript_done: Optional[Callable[[str], None]] = None,
        on_user_text: Optional[Callable[[str], None]] = None,
        on_user_text_delta: Optional[Callable[[str], None]] = None,
        on_response_done: Optional[Callable[[], None]] = None,
        on_function_call: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
        on_session_ready: Optional[Callable[[], None]] = None,
        on_status_update: Optional[Callable[[str, float], None]] = None,
    ):
        self.on_audio_delta = on_audio_delta
        self.on_text_delta = on_text_delta
        self.on_ai_transcript_done = on_ai_transcript_done
        self.on_user_text = on_user_text
        self.on_user_text_delta = on_user_text_delta
        self.on_response_done = on_response_done
        self.on_function_call = on_function_call
        self.on_session_ready = on_session_ready
        self.on_status_update = on_status_update

        self._lang = "ko"
        self._user_name: Optional[str] = None
        self._is_new_user = True
        self._preferences: Optional[str] = None   # 인식된 손님의 지난 취향 요약
        self._llm = LocalLLM()
        self._chat_tools = to_chat_tools(TOOLS)
        self._stt_hint = _stt_hint()
        self._vad = UtteranceVAD()
        self._history: list = []      # 대화 히스토리 (system 제외)
        self._utt_buffer = bytearray()
        self._busy = False            # 턴 처리 중 (STT/LLM/TTS)
        self._response_active = False
        self._cancelled = False
        self._pending_tool_outputs: dict = {}
        self._stop = asyncio.Event()
        self._connected = False

    # ── 연결/수신 루프 ──────────────────────────────────────────────────────
    async def connect(self):
        print("[LocalVoiceClient] 로컬 엔진 준비 중 (STT/TTS 로딩)...")
        await asyncio.gather(stt.preload(), tts.preload("ko"))
        self._connected = True
        print("[LocalVoiceClient] 준비 완료 (로컬 모드)")
        if self.on_session_ready:
            self.on_session_ready()

    async def listen(self):
        """RealtimeClient.listen() 대체 — 종료 신호까지 대기 (실제 처리는 콜백/태스크)."""
        await self._stop.wait()

    # ── 마이크 입력 → VAD → 턴 처리 ─────────────────────────────────────────
    async def send_audio_chunk(self, pcm_bytes: bytes):
        if not self._connected or self._busy:
            return
        events = self._vad.process(pcm_bytes)
        self._utt_buffer.extend(pcm_bytes)
        for ev in events:
            if ev == "speech_start":
                # 발화 시작 직전 0.3s(14400 bytes) 만 프리픽스로 유지 (긴 침묵 제거)
                if len(self._utt_buffer) > 14400:
                    del self._utt_buffer[:-14400]
                if self.on_status_update:
                    self.on_status_update("listening", time.time())
            elif ev == "speech_end":
                # 트림 전에 전체 발화 스냅샷 (버그방지: 여기서 잘리면 STT 빈 결과)
                snap = bytes(self._utt_buffer)
                self._utt_buffer.clear()
                self._busy = True
                if self.on_status_update:
                    self.on_status_update("processing", time.time())
                asyncio.create_task(self._run_turn(snap))
        # 발화 전 idle 상태에서만 프리롤 버퍼를 최근 0.5s 로 제한 (이벤트 없는 순수 침묵)
        if not events and not self._vad.in_speech and len(self._utt_buffer) > 48000:
            del self._utt_buffer[:-24000]

    async def _run_turn(self, audio: bytes):
        """STT → LLM(tool loop) → TTS 한 턴."""
        try:
            self._cancelled = False
            hint = self._stt_hint if self._lang != "en" else None
            text, detected = await stt.transcribe(audio, sample_rate=config.AUDIO_SAMPLE_RATE,
                                                  initial_prompt=hint)
            text = (text or "").strip()
            print(f"[LocalVoiceClient] STT: {text!r} (lang={detected})")
            if not text:
                return
            if self.on_user_text:
                self.on_user_text(text)   # main.py: 로그/언어감지/화자검증 트리거
            if self._cancelled:
                return
            self._history.append({"role": "user", "content": text})
            reply = await self._llm_turn()
            if self._cancelled or not reply:
                return
            await self._speak(reply)
        except Exception as e:
            print(f"[LocalVoiceClient] 턴 오류: {e}")
        finally:
            self._busy = False

    async def _llm_turn(self) -> str:
        """LLM 호출 + tool call 루프. 최종 어시스턴트 텍스트 반환."""
        messages = [{"role": "system",
                     "content": _system_prompt(self._lang, self._user_name, self._is_new_user,
                                               self._preferences)}]
        messages += self._history[-16:]
        for _ in range(4):   # tool 루프 최대 4회
            msg = await self._llm.chat(messages, self._chat_tools)
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id or f"call_{uuid.uuid4().hex[:8]}",
                         "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    call_id = tc.id or f"call_{uuid.uuid4().hex[:8]}"
                    name = tc.function.name
                    args = tc.function.arguments or "{}"
                    self._pending_tool_outputs.pop(call_id, None)
                    if self.on_function_call:
                        # main.py 가 handlers 실행 후 send_function_result(call_id, output) 호출
                        await self.on_function_call(call_id, name, args)
                    output = self._pending_tool_outputs.pop(call_id, "{}")
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                continue
            reply = (msg.content or "").strip()
            if reply:
                self._history.append({"role": "assistant", "content": reply})
            return reply
        return ""

    async def _speak(self, text: str):
        """텍스트 → UI 자막 + TTS 오디오 스트리밍 + 상태 이벤트."""
        self._response_active = True
        if self.on_text_delta:
            self.on_text_delta(text)
        if self.on_ai_transcript_done:
            self.on_ai_transcript_done(text)
        pcm = await tts.synthesize(text, self._lang)
        if not self._cancelled and pcm and self.on_audio_delta:
            # 100ms(4800 bytes) 단위로 잘라서 전송 → 브라우저가 순차 재생
            chunk = 4800
            for i in range(0, len(pcm), chunk):
                if self._cancelled:
                    break
                self.on_audio_delta(base64.b64encode(pcm[i:i+chunk]).decode("utf-8"))
        self._response_active = False
        if self.on_status_update:
            self.on_status_update("speaking_done", time.time())
        if self.on_response_done:
            self.on_response_done()
        if self.on_status_update:
            self.on_status_update("idle", time.time())

    # ── function call 결과 수신 (main.py 가 호출) ───────────────────────────
    async def send_function_result(self, call_id: str, output: str):
        self._pending_tool_outputs[call_id] = output

    # ── 언어/사용자/인사 ────────────────────────────────────────────────────
    async def set_language(self, lang: str):
        self._lang = "en" if lang == "en" else "ko"
        if self._lang == "en":
            asyncio.create_task(tts.preload("en"))
        print(f"[LocalVoiceClient] 언어 전환: {self._lang}")

    def _load_preferences(self, name: str):
        """등록 사용자의 지난 취향 요약을 프롬프트 개인화에 로드."""
        try:
            from src.tools.user_store import get_all_users
            for u in get_all_users():
                if u.get("name") == name and u.get("preferences"):
                    self._preferences = u["preferences"]
                    print(f"[LocalVoiceClient] 취향 로드: {self._preferences}")
                    return
        except Exception as e:
            print(f"[LocalVoiceClient] 취향 로드 실패: {e}")

    async def update_instructions(self, name: str):
        self._user_name = name
        self._is_new_user = False
        self._load_preferences(name)

    async def greet_returning_user(self, name: str):
        self._user_name = name
        self._is_new_user = False
        self._load_preferences(name)
        if self._busy or self._response_active:
            return
        greeting = (f"Welcome back, {name}! What can I get for you?"
                    if self._lang == "en" else f"{name}님 안녕하세요! 뭐 드릴까요?")
        self._history.append({"role": "assistant", "content": greeting})
        await self._speak(greeting)

    async def send_initial_greeting(self):
        greeting = ("Hi there! Welcome to O2O Burger, what can I get you?"
                    if self._lang == "en" else "어서오세요, 오투오버거입니다! 뭐 드릴까요?")
        self._history.append({"role": "assistant", "content": greeting})
        await self._speak(greeting)

    async def send_alert(self, instructions: str, max_wait: float = 2.0):
        """경고/안내 문장을 그대로 TTS. (문장이 이미 완성돼 있어 LLM 불필요)"""
        await self.cancel_response()
        await asyncio.sleep(0.2)
        await self._speak(instructions)

    async def cancel_response(self):
        self._cancelled = True
        self._utt_buffer.clear()
        self._vad.reset()

    async def close(self):
        self._connected = False
        self._stop.set()
        print("[LocalVoiceClient] 종료")
