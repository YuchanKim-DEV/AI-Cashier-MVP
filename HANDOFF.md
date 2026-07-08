# HANDOFF — 세션 인수인계

> **다음 세션은 CLAUDE.md 다음으로 이 파일을 가장 먼저 읽고 캐치업할 것.**
> 작업 진행마다 이 파일 갱신. 완료=체크, 새 사실=추가.

---

## 🎯 목표 (2026-07-08 시작)

1. **최대한 로컬 전환** — STT / TTS / LLM(대화·function calling)을 로컬 엔진으로 바꿔 **API 비용 0**. 마음껏 호출하고 싶음.
2. **기존 API 코드는 백업 보존** — 삭제 금지. `ENGINE_MODE=local|cloud` 플래그로 전환.
3. **할루시네이션 완화** — 현재 심함. STT/LLM/TTS 분리 + 메뉴 grounding + 엄격한 function calling으로 통제.
4. **세션 유실 대비** — 이 HANDOFF.md 계속 갱신.

---

## ⚙️ 하드웨어 (결정 변수!)

- **Apple M1 / RAM 8GB** ← 가장 큰 제약. 큰 모델 못 돌림.
- Python 3.11.9, venv에 torch 2.12.1 (**MPS 사용 가능**).
- ollama ❌ 미설치, ffmpeg ❌ 미설치 → 설치 필요.
- 8GB에서 STT+LLM+TTS+ECAPA(torch)+FastAPI 동시 구동은 메모리 압박 큼 → **작은 모델 + 지연 로딩** 필수. 턴 기반(2~5초 지연) 예상, Realtime처럼 full-duplex 아님.

---

## 🔍 조사 결과 요약

### B. 외부 유료 API 호출 지점 (전환 대상)
| # | API | 용도 | 위치 |
|---|-----|------|------|
| 1 | **OpenAI Realtime API** (`gpt-realtime-2`, voice=coral) | STT+LLM+function calling+TTS **한 스트림** | `src/realtime/client.py:28-118`, 모델 `main.py:100`. 입력 STT는 `whisper-1` 하드코딩(`client.py:100`) |
| 2 | **OpenAI Chat** (`gpt-4o-mini`) | 결제 후 선호도 요약 | `src/orchestrator/main.py:342-368` (`_save_preferences`) |
| 3 | **OpenAI TTS** (`tts-1`, voice=nova) | `/tts` 엔드포인트 (프론트에서 호출 안 되는 듯, dead 가능) | `src/frontend/app.py:147-176` |

→ **핵심 난관: Realtime API는 speech-to-speech 단일 스트림.** 로컬화하려면 `mic → VAD → STT → LLM(tool) → TTS → playback` **파이프라인으로 분리**해야 함 (아키텍처 큰 변경).

### C. 이미 로컬 (유지)
- **ECAPA-TDNN 화자인식**: 완전 로컬 확인됨 (SpeechBrain, `pretrained_models/ecapa` 캐시됨, CPU 추론, API 호출 없음). `speaker_verify.py:21-48`.
- cart/menu/payment(mock)/user_store(JSON)/audio(sounddevice)/FastAPI 모두 로컬.

### A. 시나리오 전체 (요약 — 상세는 조사 원문 참고)
- **세션**: 접속→session 생성→worker spawn. API키 없으면 세션 미시작. Realtime 연결 실패 시 재시도 없음. **WS 끊기면 자동 재연결 없음**(페이지 새로고침 필요). Ctrl+C 2번=강제종료.
- **화자인증**: 등록유저 0명이면 스킵(완전 개방). 첫 발화 매칭(≥0.18)→개인화 인사. 중간 다른 목소리(<0.22)→결제 차단+"주인 불러달라" 경고. `select_payment`/`payment` 앞에서 재검증. 버퍼 부족 시 스킵(fail-open). 모델 로드 실패 시 인증 조용히 비활성. `failed_verifications`/`locked` 스크린은 **선언만 되고 안 쓰임(dead)**.
- **언어감지**: 첫 발화 한국어→ko, 영어→en(`set_language`). ko모드에서 영어=노이즈 무시.
- **주문/카트**: recommend_menu/add/remove/view/checkout/select_payment. 없는 메뉴→error 리턴(크래시 X). UI 클릭 add_menu는 fn_handler 안 거침(중복 로직). checkout 빈 카트→차단.
- **결제**: physical_card=3초 후 처리. **app_card=항상 위치불가로 차단(하드코딩)**. MockGateway는 **항상 성공**(실패 경로 unreachable). 결제 후 선호도 요약(gpt-4o-mini) 백그라운드.
- **에러**: Realtime error 이벤트 대부분 콘솔출력만. 큐 full은 조용히 drop. WS 끊김 광범위 catch 후 세션 종료.

---

## 🛠 로컬 전환 계획 (M1 8GB 맞춤 — 미확정, 사용자 승인 대기)

| 기능 | 현재(클라우드) | 로컬 후보 (8GB 현실적) |
|------|----------------|------------------------|
| VAD(발화구간) | Realtime 서버 VAD | silero-vad 또는 webrtcvad |
| STT | Realtime(whisper-1) | **faster-whisper `small` int8** (한국어 OK, ~1GB) |
| LLM+function call | gpt-realtime-2 | **Ollama Qwen2.5-3B-Instruct Q4** (~2GB, 한국어+툴콜 강함) ← 8GB에서 가장 빠듯 |
| TTS | Realtime(coral)/tts-1 | **MeloTTS 한국어** (CPU 실시간) 또는 Kokoro/Piper |
| 화자인식 | (이미 로컬) | ECAPA 유지 |

- 전환은 `ENGINE_MODE` env로 스위치. cloud 코드 경로는 그대로 보존.
- 메모리 압박 → 모델 지연 로딩 / 필요시 STT·TTS를 llama.cpp·whisper.cpp(Metal)로 경량화 검토.

---

## ✅ 진행 상황 (2026-07-08) — 구현 완료

**확정 로컬 스택** (각각 단독 테스트 통과):
- STT: faster-whisper `small` int8 ✅
- LLM: Ollama `qwen2.5:3b` (OpenAI호환 + tool calling) ✅ — 툴콜 정확
- TTS: transformers VITS `facebook/mms-tts-kor` + uroman ✅ — 2.9s 음성 생성
  - ⚠️ MMS 한국어는 romanization 경유라 다소 로봇틱 가능. 품질 업그레이드 후보=MeloTTS
    (git 설치가 auto모드 차단됨 → 사용자 직접/수동 승인 필요)
- 화자인식: ECAPA (기존 로컬 유지)

**설치**: brew(ollama, ffmpeg) / pip(faster-whisper, webrtcvad-wheels, transformers, uroman, sherpa-onnx[미사용])
**Ollama**: `ollama serve` 백그라운드 필요 + `qwen2.5:3b` pull 완료.

**구현 (src/engines/)**: config.py, stt.py, llm.py, tts.py, vad.py, local_client.py(=RealtimeClient 호환)
**통합**: main.py 팩토리 — `ENGINE_MODE=local`→LocalVoiceClient / `cloud`→RealtimeClient(백업 그대로 보존).
  api_key 체크는 cloud만, `_save_preferences`도 local이면 Ollama. `.env`/`.env.example` 갱신 완료.

## ⏳ 남은 일
- [ ] E2E 통합 테스트 결과 확정 (VAD→STT→LLM→TTS)
- [ ] 실제 브라우저(localhost:8000) 음성 주문→결제 흐름 테스트
- [ ] TTS 한국어 품질 청취 (scratchpad/tts_test.wav) — 별로면 대안
- [ ] 메모리(8GB) 실사용 모니터링 — 압박 시 STT=base 로 낮추기
- [ ] app.py `/tts`(tts-1) 처리 — 죽은 코드로 보이나 확인
- [ ] 커밋/푸시

## 🔧 실행 (로컬 모드)
```bash
ollama serve &                         # 1) LLM 서버
source .venv/bin/activate
python3 -m src.orchestrator.main       # 2) 앱 (.env ENGINE_MODE=local)
# 백업(클라우드)로 돌리려면 .env 에서 ENGINE_MODE=cloud
```

---

## 🏪 앱 매장 주문 시나리오 (2026-07-08 추가)
`/app` 페이지에 매장 입장→메뉴→위치검증 주문 플로우 추가. (하단 탭: 🏠홈=매장주문 / 👤내정보=기존 등록위저드)
- **위치는 시뮬레이션** (실제 GPS 대신 '🏪매장 안 / 🚶매장 밖' 토글). 실서비스는 GPS로 대체.
- 흐름: 매장 입장하기 → geofence 통과 시 매장+메뉴 자동 표시 → 담기 → 주문하기 → **폰 위치==매장 위치**일 때만 결제, 아니면 차단.
- 백엔드: `src/tools/stores.py` (STORES 좌표+haversine geofence), app.py 라우트 `POST /api/store/enter`, `POST /api/app_order`.
  - 가격은 서버가 실제 메뉴로 재계산(클라 신뢰 X), 결제는 기존 MockPaymentGateway 재사용.
- 매장 추가/좌표 변경은 `stores.py`의 `STORES`만 수정. JS 시뮬 좌표는 app.py `STORE_LAT/LNG`(stores.py와 동일하게 유지).
- 테스트 완료: 입장(안→메뉴/밖→차단), 주문(안→결제성공 13500원/밖→위치불일치 차단), /app HTTP 200.

## 📝 세션 로그
- **2026-07-08**: 목표 수립. 코드베이스 시나리오+API 조사. 하드웨어 M1/8GB 확인.
  로컬 스택 확정 후 src/engines 추상화 레이어 구현, 각 엔진 단독 테스트 통과.
  main.py 팩토리로 ENGINE_MODE 스위치 통합. E2E/브라우저 테스트 단계.
