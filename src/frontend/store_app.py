"""
매장 주문 앱 시나리오 페이지 (/app/in, /app/out).

시나리오 (URL로 분리):
  /app/in  — 매장 20m 이내: 앱 켜짐(스플래시) → 위치 감지 → 매장 메뉴 자동 진입 → 주문/결제 가능
  /app/out — 매장 밖: 위치 감지 → "주변 매장 없음" → 메뉴 둘러보기는 가능, 결제는 차단

주문 방식 (우측 상단 토글):
  👆 수동 — 카테고리 가로 슬라이드, + / − 로 담기, 하단 바(개수·금액) → 바텀시트 상세/결제
  🎤 음성 — 키오스크 음성 시스템의 앱 버전 (동일 세션 파이프라인: mic WS + SSE + TTS)

카트는 서버 세션 카트 하나를 공유 → 음성으로 담고 수동으로 확인/결제 가능.
결제: 등록된 앱카드로 결제 (시뮬레이션 — 등록되어 있다고 간주).
"""

import json

from src.tools.menu import MENU_DATA
from src.tools.stores import STORES


def build_store_app_html(scenario: str, session_id: str) -> str:
    store = STORES[0]
    html = _TEMPLATE
    html = html.replace("__SESSION_ID__", session_id)
    html = html.replace("__SCENARIO__", "in" if scenario == "in" else "out")
    html = html.replace("__MENU_JSON__", json.dumps(MENU_DATA, ensure_ascii=False))
    html = html.replace("__STORE_JSON__", json.dumps(store, ensure_ascii=False))
    return html


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>O2O Burger 앱</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg:#F7F8FA; --card:#fff; --accent:#3182F6; --accent-lt:#EBF3FE;
    --green:#00B493; --green-lt:#E8FAF6; --red:#F04452; --red-lt:#FEECEC;
    --text:#191F28; --text2:#4E5968; --muted:#8B95A1; --border:#E5E8EB;
  }
  body {
    background: linear-gradient(135deg,#191F28 0%,#2D3748 100%);
    min-height:100vh; display:flex; align-items:center; justify-content:center;
    font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard','Noto Sans KR',sans-serif;
    padding:24px;
  }
  .phone {
    background:var(--bg); border-radius:40px; width:390px; height:800px;
    box-shadow:0 40px 80px rgba(0,0,0,.5); overflow:hidden;
    display:flex; flex-direction:column; position:relative;
  }
  .phone-bar { height:44px; background:var(--card); display:flex; align-items:center; justify-content:center;
    border-bottom:1px solid var(--border); flex-shrink:0; position:relative; z-index:5; }
  .phone-notch { width:110px; height:24px; background:#191F28; border-radius:0 0 16px 16px; }
  .phone-time { position:absolute; left:20px; font-size:.78rem; font-weight:700; color:var(--text); }

  .scr { display:none; flex:1; flex-direction:column; overflow:hidden; }
  .scr.active { display:flex; }

  /* ── 스플래시 ── */
  #scr-splash { align-items:center; justify-content:center; background:linear-gradient(160deg,#3182F6,#1B64DA); }
  .splash-logo { font-size:4.5rem; animation:pop 1.2s ease infinite alternate; }
  .splash-name { color:#fff; font-size:1.5rem; font-weight:800; margin-top:14px; letter-spacing:-.5px;
    animation:fadeup .9s ease both .3s; }
  .splash-sub  { color:rgba(255,255,255,.75); font-size:.8rem; margin-top:6px; animation:fadeup .9s ease both .55s; }
  @keyframes pop { from{transform:scale(1)} to{transform:scale(1.12)} }
  @keyframes fadeup { from{opacity:0; transform:translateY(10px)} to{opacity:1; transform:translateY(0)} }

  /* ── 위치 감지 ── */
  #scr-locating { align-items:center; justify-content:center; background:var(--bg); }
  .radar { width:110px; height:110px; border-radius:50%; position:relative; margin-bottom:22px;
    background:radial-gradient(circle,var(--accent-lt) 0%,transparent 70%); }
  .radar::before, .radar::after {
    content:''; position:absolute; inset:0; border:2px solid var(--accent); border-radius:50%;
    animation:ping 1.6s cubic-bezier(0,0,.2,1) infinite; opacity:0;
  }
  .radar::after { animation-delay:.8s; }
  .radar-pin { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:2.2rem; }
  @keyframes ping { 0%{transform:scale(.5); opacity:.8} 100%{transform:scale(1.4); opacity:0} }
  .loc-status { font-size:1rem; font-weight:700; color:var(--text); }
  .loc-sub { font-size:.8rem; color:var(--muted); margin-top:6px; text-align:center; line-height:1.6; }
  .found-banner { margin-top:18px; background:var(--green-lt); color:var(--green); border-radius:12px;
    padding:10px 18px; font-size:.85rem; font-weight:700; display:none; animation:fadeup .4s ease both; }

  /* ── 매장 없음 (out) ── */
  #scr-nostore { align-items:center; justify-content:center; padding:32px; text-align:center; }
  .nostore-icon { font-size:3.4rem; margin-bottom:14px; }
  .nostore-title { font-size:1.15rem; font-weight:800; color:var(--text); margin-bottom:8px; }
  .nostore-desc { font-size:.83rem; color:var(--muted); line-height:1.7; margin-bottom:22px; }

  /* ── 매장 화면 ── */
  #scr-store { background:var(--bg); }
  .store-head { background:linear-gradient(135deg,var(--accent),#1B64DA); color:#fff; padding:14px 18px 12px; flex-shrink:0; }
  .store-head-top { display:flex; align-items:flex-start; justify-content:space-between; }
  .store-name { font-size:1.1rem; font-weight:800; }
  .store-addr { font-size:.72rem; opacity:.85; margin-top:3px; }
  .store-badges { margin-top:8px; display:flex; gap:6px; }
  .badge { background:rgba(255,255,255,.2); border-radius:99px; padding:3px 10px; font-size:.66rem; font-weight:700; }
  .badge.out { background:rgba(240,68,82,.92); }
  .mode-btn {
    background:#fff; color:var(--accent); border:none; border-radius:12px; padding:8px 12px;
    font-size:.78rem; font-weight:800; cursor:pointer; flex-shrink:0; box-shadow:0 2px 8px rgba(0,0,0,.15);
  }

  /* 수동: 카테고리 탭 + 가로 슬라이드 */
  .cat-tabs { display:flex; gap:6px; padding:12px 16px 8px; flex-shrink:0; }
  .cat-tab { flex:1; text-align:center; padding:8px 0; border-radius:10px; font-size:.78rem; font-weight:700;
    color:var(--muted); background:var(--card); border:1px solid var(--border); cursor:pointer; }
  .cat-tab.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .slides { flex:1; display:flex; overflow-x:auto; scroll-snap-type:x mandatory; -webkit-overflow-scrolling:touch; }
  .slides::-webkit-scrollbar { display:none; }
  .slide { min-width:100%; scroll-snap-align:start; overflow-y:auto; padding:6px 16px 90px; }
  .m-item { display:flex; align-items:center; justify-content:space-between; background:var(--card);
    border:1px solid var(--border); border-radius:14px; padding:13px 14px; margin-bottom:9px; }
  .m-name { font-size:.9rem; font-weight:700; color:var(--text); }
  .m-desc { font-size:.72rem; color:var(--muted); margin-top:2px; }
  .m-price { font-size:.8rem; color:var(--text2); margin-top:3px; font-weight:600; }
  .m-add { width:32px; height:32px; border-radius:10px; border:none; background:var(--accent-lt); color:var(--accent);
    font-size:1.15rem; font-weight:800; cursor:pointer; }
  .qty { display:flex; align-items:center; gap:9px; }
  .qty button { width:28px; height:28px; border-radius:8px; border:1px solid var(--border); background:#fff;
    font-size:1rem; font-weight:700; color:var(--text2); cursor:pointer; }
  .qty span { font-size:.9rem; font-weight:800; min-width:16px; text-align:center; }

  /* 음성 모드 */
  #mode-voice { flex:1; display:none; flex-direction:column; overflow:hidden; }
  .v-status { display:flex; align-items:center; gap:8px; margin:14px 16px 8px; background:var(--card);
    border:1px solid var(--border); border-radius:12px; padding:10px 14px; flex-shrink:0; }
  .v-dot { width:10px; height:10px; border-radius:50%; background:var(--muted); }
  .v-dot.listening { background:var(--green); box-shadow:0 0 0 4px var(--green-lt); animation:pop .8s infinite alternate; }
  .v-dot.processing { background:#F5A623; }
  .v-text { font-size:.8rem; font-weight:700; color:var(--text2); }
  .v-chat { flex:1; overflow-y:auto; padding:6px 16px 90px; }
  .v-msg { max-width:82%; border-radius:14px; padding:9px 13px; font-size:.83rem; line-height:1.55; margin-bottom:8px; }
  .v-msg.user { background:var(--accent); color:#fff; margin-left:auto; border-bottom-right-radius:4px; }
  .v-msg.ai   { background:var(--card); border:1px solid var(--border); color:var(--text); border-bottom-left-radius:4px; }
  .v-hint { text-align:center; font-size:.75rem; color:var(--muted); margin:10px 0; line-height:1.7; }

  /* 하단 카트 바 */
  .cart-bar { position:absolute; bottom:0; left:0; right:0; background:var(--card);
    border-top:1px solid var(--border); padding:12px 18px calc(12px + env(safe-area-inset-bottom));
    display:none; align-items:center; justify-content:space-between; cursor:pointer; z-index:8;
    box-shadow:0 -6px 20px rgba(0,0,0,.06); }
  .cart-bar-info { font-size:.85rem; color:var(--text2); }
  .cart-bar-info b { color:var(--text); font-size:1rem; }
  .cart-bar-btn { background:var(--accent); color:#fff; border:none; border-radius:12px;
    padding:10px 18px; font-size:.85rem; font-weight:800; cursor:pointer; }

  /* 바텀시트 */
  .sheet-dim { position:absolute; inset:0; background:rgba(0,0,0,.4); opacity:0; pointer-events:none;
    transition:opacity .25s; z-index:9; }
  .sheet { position:absolute; left:0; right:0; bottom:0; background:var(--card); border-radius:22px 22px 0 0;
    padding:18px 20px calc(20px + env(safe-area-inset-bottom)); transform:translateY(105%);
    transition:transform .3s cubic-bezier(.3,1,.4,1); z-index:10; max-height:72%; overflow-y:auto; }
  .sheet-open .sheet { transform:translateY(0); }
  .sheet-open .sheet-dim { opacity:1; pointer-events:auto; }
  .sheet-grip { width:42px; height:4px; border-radius:2px; background:var(--border); margin:0 auto 14px; }
  .sheet-title { font-size:1rem; font-weight:800; color:var(--text); margin-bottom:12px; }
  .s-item { display:flex; align-items:center; justify-content:space-between; padding:9px 0;
    border-bottom:1px solid var(--bg); font-size:.86rem; }
  .s-total { display:flex; justify-content:space-between; padding:13px 0 4px; font-weight:800; font-size:.95rem; }
  .pay-note { background:var(--accent-lt); color:var(--accent); border-radius:10px; padding:9px 12px;
    font-size:.74rem; line-height:1.5; margin:10px 0 12px; }
  .btn-pay { width:100%; padding:14px; border:none; border-radius:14px; background:var(--accent); color:#fff;
    font-size:.95rem; font-weight:800; cursor:pointer; }
  .btn-pay:disabled { opacity:.55; }
  .btn-sub { width:100%; padding:11px; border:1.5px solid var(--border); border-radius:12px; background:#fff;
    color:var(--text2); font-size:.85rem; font-weight:700; cursor:pointer; margin-top:8px; }

  /* 결과 시트 */
  .result-wrap { text-align:center; padding:10px 0 4px; }
  .result-icon { font-size:3.2rem; margin-bottom:10px; }
  .result-title { font-size:1.15rem; font-weight:800; color:var(--text); margin-bottom:8px; }
  .result-desc { font-size:.82rem; color:var(--muted); line-height:1.7; margin-bottom:16px; }
  .result-fail { background:var(--red-lt); color:var(--red); border-radius:12px; padding:12px;
    font-size:.82rem; line-height:1.6; margin-bottom:14px; }
  .paybar { height:5px; border-radius:3px; background:var(--border); overflow:hidden; margin:14px 0; }
  .paybar-fill { height:100%; width:0%; background:var(--accent); transition:width .12s; }
</style>
</head>
<body>
<div class="phone" id="phone">
  <div class="phone-bar"><div class="phone-time">9:41</div><div class="phone-notch"></div></div>

  <!-- 1. 스플래시 (앱 켜기 애니메이션) -->
  <div class="scr active" id="scr-splash">
    <div class="splash-logo">🍔</div>
    <div class="splash-name">O2O Burger</div>
    <div class="splash-sub">목소리로 주문하는 스마트 버거</div>
  </div>

  <!-- 2. 위치 감지 -->
  <div class="scr" id="scr-locating">
    <div class="radar"><div class="radar-pin">📍</div></div>
    <div class="loc-status">내 위치 확인 중...</div>
    <div class="loc-sub">가까운 O2O Burger 매장을 찾고 있어요<br>(20m 이내 자동 연결)</div>
    <div class="found-banner" id="found-banner">✅ 오투오버거 강남점 · 20m 이내!</div>
  </div>

  <!-- 2-b. 매장 없음 (out 시나리오) -->
  <div class="scr" id="scr-nostore">
    <div class="nostore-icon">🚶</div>
    <div class="nostore-title">주변에 매장이 없어요</div>
    <div class="nostore-desc">20m 이내에 이용 가능한 O2O Burger 매장이 없습니다.<br>메뉴는 둘러볼 수 있지만,<br><b>주문·결제는 매장 안에서만 가능</b>해요.</div>
    <button class="cart-bar-btn" onclick="enterStore()">메뉴 둘러보기</button>
  </div>

  <!-- 3. 매장 + 메뉴 -->
  <div class="scr" id="scr-store">
    <div class="store-head">
      <div class="store-head-top">
        <div>
          <div class="store-name" id="st-name"></div>
          <div class="store-addr" id="st-addr"></div>
        </div>
        <button class="mode-btn" id="mode-btn" onclick="toggleMode()">🎤 음성 주문</button>
      </div>
      <div class="store-badges">
        <span class="badge">🟢 영업 중</span>
        <span class="badge" id="loc-badge">📍 매장 안</span>
        <span class="badge">💳 앱카드 등록됨</span>
      </div>
    </div>

    <!-- 수동 주문 -->
    <div id="mode-manual" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
      <div class="cat-tabs" id="cat-tabs"></div>
      <div class="slides" id="slides"></div>
    </div>

    <!-- 음성 주문 -->
    <div id="mode-voice">
      <div class="v-status">
        <div class="v-dot" id="v-dot"></div>
        <div class="v-text" id="v-text">연결 중...</div>
      </div>
      <div class="v-chat" id="v-chat">
        <div class="v-hint">🎤 이렇게 말씀해보세요<br>"치즈버거 하나랑 콜라 주세요" → "결제할게요"<br>결제는 등록된 앱카드로 진행돼요</div>
      </div>
    </div>
  </div>

  <!-- 하단 카트 바 -->
  <div class="cart-bar" id="cart-bar" onclick="openSheet()">
    <div class="cart-bar-info">상품 <b id="cb-count">0</b>개 · <b id="cb-total">0원</b></div>
    <button class="cart-bar-btn">상세 · 결제</button>
  </div>

  <!-- 바텀시트 -->
  <div class="sheet-dim" onclick="closeSheet()"></div>
  <div class="sheet" id="sheet">
    <div class="sheet-grip"></div>
    <div id="sheet-body"></div>
  </div>
</div>

<script>
const SESSION_ID = '__SESSION_ID__';
const SCENARIO   = '__SCENARIO__';            // 'in' | 'out'
const MENU       = __MENU_JSON__;
const STORE      = __STORE_JSON__;
const IN_STORE   = SCENARIO === 'in';
// 시뮬레이션 좌표: in=매장 좌표(20m 이내), out=약 1.4km 밖
const MY_LOC = IN_STORE ? { lat: STORE.lat, lng: STORE.lng }
                        : { lat: STORE.lat + 0.01, lng: STORE.lng + 0.01 };

let mode = 'manual';               // 'manual' | 'voice'
let cart = {};                     // 서버 카트 미러 { name: {qty, price} }
let cartTotal = 0;
let voiceStarted = false;
let paying = false;
let micMuted = false;              // 결제 화면(checkout~)에서 음성인식 중단

// ── 유틸 ──
function $(id){ return document.getElementById(id); }
function show(id){ document.querySelectorAll('.scr').forEach(s=>s.classList.remove('active')); $(id).classList.add('active'); }
async function post(path, data){
  try { await fetch(path, { method:'POST', headers:{'Content-Type':'application/json','X-Session-Id':SESSION_ID}, body:JSON.stringify(data||{}) }); }
  catch(e){ console.error(e); }
}

// ── 시나리오 시작: 스플래시 → 위치감지 → 분기 ──
window.addEventListener('DOMContentLoaded', () => {
  post('/action/set_location', { at_store: IN_STORE });   // 음성 결제 게이트용
  setTimeout(() => {
    show('scr-locating');
    setTimeout(() => {
      if (IN_STORE) {
        $('found-banner').style.display = 'block';
        setTimeout(enterStore, 900);                       // 자동으로 매장 메뉴 진입
      } else {
        show('scr-nostore');
      }
    }, 1600);
  }, 1900);
});

function enterStore(){
  $('st-name').textContent = STORE.name;
  $('st-addr').textContent = STORE.address + (IN_STORE ? ' · 약 8m' : ' · 약 1.4km');
  const badge = $('loc-badge');
  if (!IN_STORE) { badge.textContent = '🔴 매장 밖'; badge.classList.add('out'); }
  renderMenu();
  show('scr-store');
  $('cart-bar').style.display = 'flex';
  updateCartBar();
  startSSE();
}

// ── 수동 주문: 카테고리 슬라이드 ──
const CATS = Object.keys(MENU);
function renderMenu(){
  $('cat-tabs').innerHTML = CATS.map((c,i)=>`<div class="cat-tab${i===0?' on':''}" id="tab-${i}" onclick="goCat(${i})">${c}</div>`).join('');
  $('slides').innerHTML = CATS.map(c=>`<div class="slide">` + MENU[c].map(it=>`
    <div class="m-item">
      <div>
        <div class="m-name">${it.name}</div>
        ${it.includes?`<div class="m-desc">${it.includes}</div>`:''}
        <div class="m-price">${it.price.toLocaleString()}원</div>
      </div>
      <div id="ctl-${it.id}"><button class="m-add" onclick="addItem('${it.name}')">+</button></div>
    </div>`).join('') + `</div>`).join('');
  $('slides').addEventListener('scroll', () => {
    const i = Math.round($('slides').scrollLeft / $('slides').clientWidth);
    CATS.forEach((_,k)=>$('tab-'+k)?.classList.toggle('on', k===i));
  }, { passive:true });
}
function goCat(i){ $('slides').scrollTo({ left: i*$('slides').clientWidth, behavior:'smooth' }); }

function itemId(name){ for(const c of CATS) for(const it of MENU[c]) if(it.name===name) return it.id; return null; }
function addItem(name){ post('/action/add_menu', { name }); }       // 서버 카트가 진실 → SSE로 반영
function decItem(name){ post('/action/remove_menu', { name }); }

function renderControls(){
  for (const c of CATS) for (const it of MENU[c]) {
    const ctl = $('ctl-'+it.id); if (!ctl) continue;
    const q = cart[it.name]?.qty || 0;
    ctl.innerHTML = q>0
      ? `<div class="qty"><button onclick="decItem('${it.name}')">−</button><span>${q}</span><button onclick="addItem('${it.name}')">+</button></div>`
      : `<button class="m-add" onclick="addItem('${it.name}')">+</button>`;
  }
}
function updateCartBar(){
  const count = Object.values(cart).reduce((a,b)=>a+b.qty,0);
  $('cb-count').textContent = count;
  $('cb-total').textContent = cartTotal.toLocaleString()+'원';
}

// ── SSE: 서버 세션 상태(카트/대화/화면) 동기화 ──
let _prevScreen = '';
function startSSE(){
  const es = new EventSource('/events?sid='+SESSION_ID);
  es.onmessage = (e) => {
    let st; try { st = JSON.parse(e.data); } catch { return; }
    // 카트 미러
    cart = {}; cartTotal = st.cart_total || 0;
    (st.cart_items||[]).forEach(i => cart[i.name] = { qty:i.quantity, price:i.price });
    renderControls(); updateCartBar();
    if ($('sheet').classList ? document.querySelector('.phone').classList.contains('sheet-open') && !paying : false) renderSheetCart();
    // 결제 화면부터 음성인식 중단 — 메뉴로 돌아와야 재개
    micMuted = ['checkout','payment_processing','complete','card_insert'].includes(st.screen);
    // 음성 상태
    const dot=$('v-dot'), vt=$('v-text');
    if (dot) {
      if (micMuted) {
        dot.className = 'v-dot';
        vt.textContent = '🔇 결제 중 — 음성인식 일시중지 (메뉴로 돌아가면 재개)';
      } else {
        dot.className = 'v-dot ' + (st.conversation==='listening'?'listening':st.conversation==='processing'?'processing':'');
        vt.textContent = {listening:'듣고 있어요 — 말씀하세요', processing:'생각 중...', idle:'대기 중 — 말씀하세요'}[st.conversation] || '대기 중';
      }
    }
    renderChat(st.conversation_log||[]);
    // 음성 결제 흐름 화면 반영
    if (st.screen !== _prevScreen) {
      if (st.screen === 'checkout' && mode==='voice') { openSheet(); }
      if (st.screen === 'payment_processing') { showPayingSheet(); }
      if (st.screen === 'complete') { showResultSheet(true, st.transaction_id || ''); }
      _prevScreen = st.screen;
    }
  };
}
function renderChat(log){
  const box = $('v-chat'); if (!box) return;
  const msgs = log.slice(-8).map(m=>`<div class="v-msg ${m.role==='user'?'user':'ai'}">${m.text}</div>`).join('');
  if (box.dataset.last !== msgs) { box.dataset.last = msgs;
    box.innerHTML = `<div class="v-hint">🎤 이렇게 말씀해보세요<br>"치즈버거 하나랑 콜라 주세요" → "결제할게요"<br>결제는 등록된 앱카드로 진행돼요</div>` + msgs;
    box.scrollTop = box.scrollHeight; }
}

// ── 음성/수동 전환 (우측 상단) ──
function toggleMode(){
  mode = mode==='manual' ? 'voice' : 'manual';
  $('mode-manual').style.display = mode==='manual' ? 'flex' : 'none';
  $('mode-voice').style.display  = mode==='voice'  ? 'flex' : 'none';
  $('mode-btn').textContent      = mode==='manual' ? '🎤 음성 주문' : '👆 수동 주문';
  if (mode==='voice') startVoice(); else stopVoiceAudio();
}

// ── 음성 파이프라인 (키오스크 앱 버전: mic WS + audio out WS) ──
let _audioWs=null, _audioCtx=null, _outWs=null, _nextPlay=0, _micStarted=false;
async function startVoice(){
  if (!voiceStarted) { voiceStarted = true; await post('/action/start', {}); }
  startAudioOut(); startMic();
}
async function startMic(){
  if (_micStarted) return; _micStarted = true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio:{ channelCount:1, echoCancellation:true, noiseSuppression:true } });
    const ctx = new AudioContext({ sampleRate:48000 }); await ctx.resume();
    _audioWs = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws/audio?sid='+SESSION_ID);
    _audioWs.binaryType='arraybuffer';
    const src = `class P extends AudioWorkletProcessor{constructor(){super();this.b=[]}process(i){const c=i[0][0];if(!c)return true;for(let k=0;k<c.length;k++)this.b.push(c[k]);if(this.b.length>=4800){this.port.postMessage(new Float32Array(this.b.splice(0,4800)))}return true}}registerProcessor('p',P);`;
    const url = URL.createObjectURL(new Blob([src],{type:'application/javascript'}));
    await ctx.audioWorklet.addModule(url); URL.revokeObjectURL(url);
    const node = new AudioWorkletNode(ctx,'p');
    node.port.onmessage = ({data:f32}) => {
      if (!_audioWs || _audioWs.readyState!==1 || micMuted) return;   // 결제 화면 = 마이크 차단
      const out = new Int16Array(f32.length>>1);
      for (let i=0;i<out.length;i++){ const s=Math.max(-1,Math.min(1,(f32[i*2]+f32[i*2+1])*.5)); out[i]=s<0?s*0x8000:s*0x7FFF; }
      _audioWs.send(out.buffer);
    };
    ctx.createMediaStreamSource(stream).connect(node);
  } catch(e){ _micStarted=false; alert('마이크 권한을 허용해주세요.'); }
}
function startAudioOut(){
  if (_outWs) return;
  _audioCtx = new AudioContext({ sampleRate:24000 }); _nextPlay=0;
  _outWs = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws/audio_out?sid='+SESSION_ID);
  _outWs.binaryType='arraybuffer';
  _outWs.onmessage = ({data}) => {
    if (!_audioCtx || mode!=='voice') return;
    if (_audioCtx.state==='suspended') _audioCtx.resume();
    const p = new Int16Array(data); if (!p.length) return;
    const f = new Float32Array(p.length);
    for (let i=0;i<p.length;i++) f[i]=p[i]/32768;
    const buf=_audioCtx.createBuffer(1,f.length,24000); buf.getChannelData(0).set(f);
    const s=_audioCtx.createBufferSource(); s.buffer=buf; s.playbackRate.value=1.35; s.connect(_audioCtx.destination);
    const t=Math.max(_nextPlay,_audioCtx.currentTime+0.08); s.start(t); _nextPlay=t+buf.duration/1.35;
  };
}
function stopVoiceAudio(){ if (_audioCtx){ _audioCtx.close().catch(()=>{}); _audioCtx=null; } if(_outWs){ _outWs.close(); _outWs=null; } }

// ── 바텀시트 (상세 + 결제) ──
function openSheet(){ renderSheetCart(); $('phone').classList.add('sheet-open'); }
function closeSheet(){
  if (paying) return;
  $('phone').classList.remove('sheet-open');
  post('/action/back_to_menu', {});   // 메뉴 복귀 → 음성인식 재개
}
function renderSheetCart(){
  const names = Object.keys(cart);
  if (!names.length) {
    $('sheet-body').innerHTML = `<div class="sheet-title">장바구니</div><div class="result-desc" style="text-align:center;padding:16px 0;">아직 담긴 메뉴가 없어요!</div>`;
    return;
  }
  const rows = names.map(n=>`
    <div class="s-item">
      <div>${n} <span style="color:var(--muted);font-size:.76rem;">${cart[n].price.toLocaleString()}원</span></div>
      <div class="qty"><button onclick="decItem('${n}')">−</button><span>${cart[n].qty}</span><button onclick="addItem('${n}')">+</button></div>
    </div>`).join('');
  $('sheet-body').innerHTML = `
    <div class="sheet-title">주문 상세</div>
    ${rows}
    <div class="s-total"><span>총 결제금액</span><span>${cartTotal.toLocaleString()}원</span></div>
    <div class="pay-note">💳 <b>등록된 앱카드</b>로 결제됩니다 (시뮬레이션)${IN_STORE?'':' · 📍 현재 매장 밖'}</div>
    <button class="btn-pay" onclick="payNow()">앱카드로 ${cartTotal.toLocaleString()}원 결제</button>
    <button class="btn-sub" onclick="closeSheet()">계속 담기</button>`;
}

// ── 결제 (수동): 서버가 20m geofence 재검증 ──
async function payNow(){
  if (paying) return;
  const items = Object.keys(cart).map(n=>({ name:n, qty:cart[n].qty }));
  if (!items.length) return;
  paying = true;
  showPayingSheet();
  try {
    const r = await (await fetch('/api/app_order', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ store_id: STORE.id, items, lat: MY_LOC.lat, lng: MY_LOC.lng }),
    })).json();
    // 진행바 잠깐 채우고 결과 표시
    setTimeout(() => {
      paying = false;
      if (r.ok) { showResultSheet(true, r.transaction_id); post('/action/reset', {}); }
      else if (r.reason === 'location_mismatch') showResultSheet(false, r.message || '매장 20m 이내에서만 결제할 수 있어요.');
      else showResultSheet(false, r.message || r.error || '결제에 실패했어요.');
    }, 1200);
  } catch(e){ paying=false; showResultSheet(false, e.message); }
}
function showPayingSheet(){
  $('sheet-body').innerHTML = `
    <div class="result-wrap">
      <div class="result-icon">💳</div>
      <div class="result-title">앱카드 결제 중...</div>
      <div class="paybar"><div class="paybar-fill" id="pf"></div></div>
      <div class="result-desc">등록된 앱카드로 안전하게 결제하고 있어요</div>
    </div>`;
  $('phone').classList.add('sheet-open');
  let p=0; const iv=setInterval(()=>{ p+=9; const el=$('pf'); if(el) el.style.width=Math.min(p,95)+'%'; if(p>=100) clearInterval(iv); },100);
}
function showResultSheet(ok, detail){
  paying = false;
  $('sheet-body').innerHTML = ok ? `
    <div class="result-wrap">
      <div class="result-icon">🎉</div>
      <div class="result-title">결제 완료!</div>
      <div class="result-desc">${STORE.name}<br>등록된 앱카드로 결제되었어요${detail?'<br>'+detail:''}<br>음식이 준비되면 알려드릴게요!</div>
      <button class="btn-pay" onclick="location.reload()">처음으로</button>
    </div>` : `
    <div class="result-wrap">
      <div class="result-icon">📍</div>
      <div class="result-title">결제할 수 없어요</div>
      <div class="result-fail">${detail}</div>
      <div class="result-desc">매장 20m 이내에서만 주문·결제가 가능해요.<br>매장 안 시나리오: <b>/app/in</b></div>
      <button class="btn-sub" onclick="closeSheet()">돌아가기</button>
    </div>`;
  $('phone').classList.add('sheet-open');
}
</script>
</body>
</html>"""
