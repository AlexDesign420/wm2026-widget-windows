const SERVER_URL = "http://127.0.0.1:9876";

const COUNTRY_FLAGS = {
  DE: "🇩🇪", GB: "🇬🇧", CA: "🇨🇦", AT: "🇦🇹", CH: "🇨🇭", FR: "🇫🇷", IT: "🇮🇹",
  NL: "🇳🇱", BE: "🇧🇪", US: "🇺🇸", PT: "🇵🇹", IE: "🇮🇪", NO: "🇳🇴", SE: "🇸🇪",
  FI: "🇫🇮", DK: "🇩🇰", ES: "🇪🇸", JP: "🇯🇵", AU: "🇦🇺", AR: "🇦🇷", MX: "🇲🇽",
  BR: "🇧🇷", QA: "🇶🇦", TR: "🇹🇷", EU: "🇪🇺",
};

const state = {
  today: [],
  schedule: [],
  feed: [],
  audioOn: false,
  shift: false,
  serverOnline: false,
  serverError: "",
  serverStreams: [],
  serverAudio: { playing: false, url: null, volume: 70 },
  serverTicker: [],
  serverComments: [],
  serverCommentary: [],
  commentsEnabled: true,
  commentsExpanded: false,
  expanded: false,
  sidePanelOpen: false,
  widgetHidden: false,
  wallpaper: "",
};

try { state.sidePanelOpen = localStorage.getItem("wm2026SidePanelOpen") === "1"; } catch (e) {}
try { state.widgetHidden = localStorage.getItem("wm2026Hidden") === "1"; } catch (e) {}
try { state.expanded = localStorage.getItem("wm2026Expanded") === "1"; } catch (e) {}
try { state.commentsExpanded = localStorage.getItem("wm2026CommentsExpanded") === "1"; } catch (e) {}

function persist(key, value) {
  try { localStorage.setItem(key, value); } catch (e) {}
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function slugLabel(value) {
  if (!value) return "";
  return value
    .replace("group-stage", "Gruppe")
    .replace("group-", "Gr.")
    .replace("round-of-16", "Achtelfinale")
    .replace("quarterfinal", "Viertelfinale")
    .replace("semifinal", "Halbfinale")
    .replace("final", "Finale");
}

function countdown(target) {
  const delta = target - new Date();
  if (delta <= 0) return null;
  return {
    d: Math.floor(delta / 86400000),
    h: Math.floor((delta % 86400000) / 3600000),
    m: Math.floor((delta % 3600000) / 60000),
  };
}

function mapGame(event) {
  const comp = (event.competitions || [])[0] || {};
  const st = (comp.status || {}).type || {};
  const cs = comp.competitors || [];
  const h = cs.find((c) => c.homeAway === "home") || cs[0] || {};
  const a = cs.find((c) => c.homeAway === "away") || cs[1] || {};
  return {
    id: event.id,
    date: new Date(event.date),
    state: st.state || "pre",
    desc: st.shortDetail || "",
    clock: (comp.status || {}).displayClock || "",
    group: (event.season || {}).slug || "",
    h: {
      short: (h.team || {}).shortDisplayName || "–",
      logo: (h.team || {}).logo || "",
      score: h.score || "0",
      w: h.winner || false,
    },
    a: {
      short: (a.team || {}).shortDisplayName || "–",
      logo: (a.team || {}).logo || "",
      score: a.score || "0",
      w: a.winner || false,
    },
    venue: ((comp.venue || {}).fullName) || "",
    city: (((comp.venue || {}).address) || {}).city || "",
  };
}

function groupByDay(games) {
  const groups = new Map();
  for (const game of games) {
    const key = game.date.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(game);
  }
  return [...groups.entries()];
}

async function fetchJson(path, fallback) {
  const response = await fetch(`${SERVER_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json().catch(() => fallback);
}

async function refresh() {
  try {
    const [status, streams, ticker, comments, commentary, todayData, scheduleData, feedData] = await Promise.all([
      fetchJson("/api/status", {}),
      fetchJson("/api/streams", { streams: [] }),
      fetchJson("/api/ticker", { ticker: [] }),
      fetchJson("/api/comments", { enabled: true, comments: [] }),
      fetchJson("/api/commentary", { commentary: [] }),
      fetchJson("/api/today", { events: [] }),
      fetchJson("/api/schedule", { events: [] }),
      fetchJson("/api/feed", { feed: [] }),
    ]);

    state.serverOnline = true;
    state.serverError = "";
    state.serverStreams = streams.streams || [];
    state.serverAudio = status.audio || state.serverAudio;
    state.serverTicker = ticker.ticker || [];
    state.serverComments = comments.comments || [];
    state.serverCommentary = commentary.commentary || [];
    state.commentsEnabled = comments.enabled !== false;
    state.today = todayData.events || [];
    state.schedule = scheduleData.events || [];
    state.feed = feedData.feed || [];
    state.audioOn = status.audio_on === true;
    state.shift = status.shifted === true;
    state.wallpaper = status.wallpaper || state.wallpaper;
    if (!state.sidePanelOpen && status.shifted === true) {
      state.sidePanelOpen = true;
      persist("wm2026SidePanelOpen", "1");
    }
  } catch (error) {
    state.serverOnline = false;
    state.serverError = String(error);
  }
  render();
}

async function post(path, payload = {}) {
  const response = await fetch(`${SERVER_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json().catch(() => ({}));
}

const WM2026 = {
  toggleHidden() {
    state.widgetHidden = !state.widgetHidden;
    persist("wm2026Hidden", state.widgetHidden ? "1" : "0");
    render();
  },
  toggleExpand() {
    state.expanded = !state.expanded;
    persist("wm2026Expanded", state.expanded ? "1" : "0");
    render();
  },
  toggleCommentsExpand() {
    state.commentsExpanded = !state.commentsExpanded;
    persist("wm2026CommentsExpanded", state.commentsExpanded ? "1" : "0");
    render();
  },
  async toggleSidePanel() {
    state.sidePanelOpen = !state.sidePanelOpen;
    persist("wm2026SidePanelOpen", state.sidePanelOpen ? "1" : "0");
    render();
    await post("/api/shift", { dir: state.sidePanelOpen ? "right" : "left" }).catch(() => {});
    setTimeout(refresh, 250);
  },
  async openMagenta() {
    await post("/api/open_magentatv").catch(() => {});
  },
  async toggleAudio() {
    state.audioOn = !state.audioOn;
    render();
    await post("/api/audio_on/toggle", { enabled: state.audioOn }).catch(() => {});
  },
  async testAudio() {
    await post("/api/test_audio").catch(() => {});
  },
  async playStream(url) {
    state.serverAudio = { playing: true, url, volume: state.serverAudio.volume || 70 };
    render();
    const data = await post("/api/play", { url, volume: state.serverAudio.volume || 70 }).catch(() => ({}));
    if (data.audio) state.serverAudio = data.audio;
    render();
  },
  async stopAudio() {
    state.serverAudio = { playing: false, url: null, volume: state.serverAudio.volume || 70 };
    render();
    const data = await post("/api/stop").catch(() => ({}));
    if (data.audio) state.serverAudio = data.audio;
    render();
  },
  async setVolume(level) {
    state.serverAudio.volume = Math.max(0, Math.min(100, level));
    render();
    const data = await post("/api/volume", { level: state.serverAudio.volume }).catch(() => ({}));
    if (data.audio) state.serverAudio = data.audio;
    render();
  },
  async toggleComments() {
    state.commentsEnabled = !state.commentsEnabled;
    render();
    await post("/api/comments/toggle", { enabled: state.commentsEnabled }).catch(() => {});
    if (!state.commentsEnabled) state.serverComments = [];
    render();
  },
};

window.WM2026 = WM2026;

function renderGameCard(game) {
  const isLive = game.state === "in";
  const isPost = game.state === "post";
  return `
    <div class="game ${isLive ? "game-live" : ""}">
      <div class="g-top">
        <div class="g-status ${isLive ? "g-live" : isPost ? "g-post" : "g-pre"}">
          ${isLive ? '<span class="ldot"></span>' : ""}
          ${esc(isLive ? `LIVE · ${game.clock}` : isPost ? `✓ ${game.desc}` : game.desc)}
        </div>
        ${game.group ? `<div class="g-tag">${esc(slugLabel(game.group))}</div>` : ""}
      </div>
      <div class="g-teams">
        <div class="team">
          ${game.h.logo ? `<img class="logo" src="${esc(game.h.logo)}" alt="" />` : ""}
          <div class="ti"><div class="tn ${isPost && game.h.w ? "tn-w" : isPost && !game.h.w ? "tn-l" : ""}">${esc(game.h.short)}</div></div>
        </div>
        <div class="scorebox">
          ${game.state !== "pre"
            ? `<div class="snums"><span class="sc">${esc(game.h.score)}</span><span class="ssep">:</span><span class="sc">${esc(game.a.score)}</span></div>`
            : '<div class="snums"><span class="vs">vs</span></div>'}
        </div>
        <div class="team team-r">
          ${game.a.logo ? `<img class="logo" src="${esc(game.a.logo)}" alt="" />` : ""}
          <div class="ti"><div class="tn ${isPost && game.a.w ? "tn-w" : isPost && !game.a.w ? "tn-l" : ""}">${esc(game.a.short)}</div></div>
        </div>
      </div>
      ${game.venue ? `<div class="venue">🏟 ${esc(game.venue)}${game.city ? ` · ${esc(game.city)}` : ""}</div>` : ""}
    </div>
  `;
}

function renderSidePanel(liveGames, width) {
  return `
    <div class="side-panel ${state.sidePanelOpen ? "open" : ""}" style="left:${width}px">
      <div class="sp-inner">
        <div class="sp-hdr">
          <span class="sp-title">
            ${liveGames.length > 0 ? '<span style="color:#ef4444;animation:pulse 1.6s infinite;display:inline-block">●</span>' : "📺"}
            &nbsp;Live-Ticker
            ${state.serverCommentary.length > 0 ? `<span style="background:#21262d;color:#9aa5c2;font-size:9px;padding:1px 6px;border-radius:6px;font-weight:800">${state.serverCommentary.length}</span>` : ""}
          </span>
          <span class="sp-close" onclick="WM2026.toggleSidePanel()">✕</span>
        </div>
        <div class="sp-scroll">
          ${liveGames.length === 0 && state.serverCommentary.length === 0 && state.serverComments.length === 0 ? `
            <div class="sp-empty">
              Kein Spiel aktiv.<br />
              Der Ticker erscheint sobald<br />
              ein Spiel laeuft.
            </div>` : ""}

          ${liveGames.length > 0 ? `
            <div>
              <div class="sp-sec">🔴 Jetzt live</div>
              ${liveGames.map((game) => `
                <div class="sp-ticker-item sp-ticker-live">
                  <div style="flex:1">
                    <div class="sp-ticker-teams">${esc(game.home)} – ${esc(game.away)}</div>
                    ${game.detail ? `<div style="font-size:9px;color:#34d399;margin-top:2px">${esc(game.detail)}</div>` : ""}
                  </div>
                  <div class="sp-ticker-score">${esc(game.home_score)}:${esc(game.away_score)}</div>
                  <div class="sp-ticker-clock">${esc(game.clock)}</div>
                </div>`).join("")}
            </div>` : ""}

          ${state.serverCommentary.length > 0 ? `
            <div>
              <div class="sp-sec">📝 Ereignisse</div>
              ${state.serverCommentary.slice().reverse().map((event) => {
                const type = (event.type || "").toLowerCase();
                const text = event.text || "";
                let cls = "sp-event";
                if (type.includes("goal") || type.includes("tor") || text.includes("⚽")) cls += " sp-event-goal";
                else if (type.includes("red") || type.includes("rot")) cls += " sp-event-card-r";
                else if (type.includes("yellow") || type.includes("gelb")) cls += " sp-event-card-y";
                else if (type.includes("sub") || type.includes("wechsel")) cls += " sp-event-sub";
                return `
                  <div class="${cls}">
                    ${event.match ? `<div class="sp-match">${esc(event.match)}</div>` : ""}
                    ${event.clock ? `<div class="sp-clock">${esc(event.clock)}</div>` : ""}
                    <div class="sp-text">${esc(text)}</div>
                  </div>`;
              }).join("")}
            </div>` : ""}

          ${state.serverComments.length > 0 ? `
            <div>
              <div class="sp-sec">💬 Kommentare</div>
              ${state.serverComments.map((comment) => `
                <div class="sp-comment">
                  <div class="sp-comment-src">${esc(comment.source || "kicker")}</div>
                  <div class="sp-comment-txt">${esc(comment.text || "")}</div>
                </div>`).join("")}
            </div>` : ""}
        </div>
      </div>
    </div>
  `;
}

function renderStatusBanner() {
  if (state.serverOnline) return "";
  return `
    <div class="status-banner">
      <b>Server offline</b><br />
      Starte <code>start_server.bat</code> oder <code>start_server_hidden.vbs</code> im Windows-Ordner.<br />
      <span style="color:#6b7280">${esc(state.serverError)}</span>
    </div>
  `;
}

let _scrollTop = 0;
let _mx = null, _my = null;
const _drag = { el: null, y: 0, top: 0 };
const _scrollSel = ".scroll, .sp-scroll, .streams-scroll, .comments-list";
function _scrollTarget() {
  if (_mx != null) {
    const t = document.elementFromPoint(_mx, _my);
    const el = t && t.closest(_scrollSel);
    if (el) return el;
  }
  return document.querySelector(".scroll");
}
document.addEventListener("mousedown", (e) => {
  const el = e.target.closest(_scrollSel);
  if (el) { _drag.el = el; _drag.y = e.clientY; _drag.top = el.scrollTop; }
});
document.addEventListener("mousemove", (e) => {
  _mx = e.clientX; _my = e.clientY;
  if (!_drag.el) return;
  _drag.el.scrollTop = _drag.top - (e.clientY - _drag.y);
  if (_drag.el.classList.contains("scroll")) _scrollTop = _drag.el.scrollTop;
});
document.addEventListener("mouseup", () => { _drag.el = null; });
try {
  const _es = new EventSource(`${SERVER_URL}/api/wheel_stream`);
  _es.onmessage = (ev) => {
    const el = _scrollTarget();
    if (!el) return;
    el.scrollTop -= (parseInt(ev.data, 10) || 0);
    if (el.classList.contains("scroll")) _scrollTop = el.scrollTop;
  };
} catch (e) {}

// Edge auto-scroll: relies only on mouse-move, which Lively forwards (wheel is not).
setInterval(() => {
  if (_drag.el || _mx == null) return;
  const t = document.elementFromPoint(_mx, _my);
  const el = t && t.closest(_scrollSel);
  if (!el) return;
  const r = el.getBoundingClientRect();
  const zone = Math.max(30, Math.min(80, r.height * 0.18));
  let d = 0;
  if (_my > r.bottom - zone) d = Math.ceil(((_my - (r.bottom - zone)) / zone) * 16) + 3;
  else if (_my < r.top + zone) d = -(Math.ceil((((r.top + zone) - _my) / zone) * 16) + 3);
  if (!d) return;
  el.scrollTop += d;
  if (el.classList.contains("scroll")) _scrollTop = el.scrollTop;
}, 16);

function render() {
  const _prev = document.querySelector(".scroll");
  if (_prev) _scrollTop = _prev.scrollTop;
  if (state.wallpaper) {
    document.body.style.backgroundImage = `url("${SERVER_URL}/api/wallpaper_image?u=${encodeURIComponent(state.wallpaper)}"), var(--bg-body)`;
  } else {
    document.body.style.backgroundImage = "";
  }

  const screenWidth = window.innerWidth || 2560;
  const width = screenWidth < 1280 ? 340 : screenWidth < 1440 ? 380 : screenWidth < 1920 ? 420 : screenWidth < 2560 ? 470 : screenWidth < 3840 ? 520 : 580;
  const rootClass = [
    "wm2026-root",
    state.widgetHidden ? "hidden" : "",
    width <= 340 ? "wm2026-sm" : "",
  ].filter(Boolean).join(" ");

  const todayGames = state.today.map(mapGame);
  const scheduleGames = state.schedule.map(mapGame);
  const live = todayGames.filter((game) => game.state === "in");
  const pre = todayGames.filter((game) => game.state === "pre");
  const post = todayGames.filter((game) => game.state === "post");
  const totalPlayed = scheduleGames.filter((game) => game.state === "post").length;
  const now = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const cd = countdown(new Date("2026-06-11T18:00:00"));
  const todayKey = new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });
  const days = groupByDay(scheduleGames);
  const liveGames = state.serverTicker.filter((game) => game.state === "in");
  const onlineStreams = state.serverStreams.filter((stream) => stream.online);

  document.getElementById("app").innerHTML = `
    <div class="${rootClass}">
      <div class="notch" onclick="WM2026.toggleHidden()">
        ${live.length > 0 ? '<span class="notch-live"></span>' : ""}
        <span class="notch-ball">⚽</span>
        <span class="notch-label">WM 2026</span>
        <span class="notch-chev">▶</span>
      </div>

      <div class="widget-shell" style="width:${width}px">
        <div class="widget" style="width:${width}px">
          <div class="hdr">
            <div class="hdr-l">
              <div class="ball">⚽</div>
              <div>
                <div class="h-title">WM 2026</div>
                <div class="h-sub">USA · Kanada · Mexiko · <b>104 Spiele</b></div>
              </div>
            </div>
            <div class="h-r">
              ${live.length > 0 ? '<div class="h-badge">● LIVE</div>' : ""}
              <div class="h-time">⟳ ${esc(now)}</div>
              <div class="h-r-btns">
                <span class="sp-toggle" onclick="WM2026.toggleSidePanel()">${state.sidePanelOpen ? "◀ Ticker" : "Ticker ▶"}</span>
                <span class="hide-btn" onclick="WM2026.toggleHidden()">✕ Ausblenden</span>
              </div>
            </div>
          </div>

          <div class="ctl">
            <div class="ctl-row">
              <div class="btn btn-magenta" onclick="WM2026.openMagenta()">📺 MagentaTV</div>
              <div class="btn ${state.audioOn ? "btn-audio-on" : "btn-audio-off"}" onclick="WM2026.toggleAudio()">
                ${state.audioOn ? "🔊 Tor-Sound AN" : "🔇 Tor-Sound AUS"}
              </div>
              <div class="btn btn-test" onclick="WM2026.testAudio()">▶ Test</div>
            </div>

            ${live.length > 0 ? `
              <div>
                <div class="wlbl">🔴 Jetzt live — Stream waehlen</div>
                ${live.map((game) => `
                  <div class="wgame wgame-live">
                    <div class="wg-teams">${esc(game.h.short)} <span class="wg-score">${esc(game.h.score)}:${esc(game.a.score)}</span> ${esc(game.a.short)}</div>
                    <div class="wg-clock">${esc(game.clock)}</div>
                    <div class="wg-btn" onclick="WM2026.openMagenta()">▶ Stream</div>
                  </div>`).join("")}
              </div>` : pre.length > 0 ? `
              <div>
                <div class="wlbl">📺 Heute noch</div>
                ${pre.slice(0, 3).map((game) => `
                  <div class="wgame">
                    <div class="wg-teams">${esc(game.h.short)} vs ${esc(game.a.short)}</div>
                    <div class="wg-clock">${game.date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}</div>
                  </div>`).join("")}
              </div>` : ""}
          </div>

          <div class="livewrap ${state.expanded ? "expanded" : ""}">
            <div class="live-toggle" onclick="WM2026.toggleExpand()">
              <span class="lt-l">
                📻 Live-Audio &amp; Streams
                ${state.serverAudio.playing ? '<span class="lt-live">● WIEDERGABE</span>' : ""}
                ${onlineStreams.length > 0 ? `<span class="lt-badge">${onlineStreams.length}</span>` : ""}
              </span>
              <span class="chev">▾</span>
            </div>
            <div class="livepanel">
              <div class="live-actions">
                <div class="la-row">
                  ${state.serverAudio.playing
                    ? '<div class="la-btn la-on la-flex" onclick="WM2026.stopAudio()">⏹ Stop</div>'
                    : '<div class="la-btn la-off la-flex">🔇 Gestoppt</div>'}
                  <div class="la-btn la-test" onclick="WM2026.setVolume(${Math.max(0, (state.serverAudio.volume || 70) - 10)})">−</div>
                  <div class="la-btn" style="font-size:11px;color:#9aa5c2;flex:0 0 auto;padding:9px 8px">${state.serverAudio.volume || 70}%</div>
                  <div class="la-btn la-test" onclick="WM2026.setVolume(${Math.min(100, (state.serverAudio.volume || 70) + 10)})">+</div>
                </div>

                <div class="wlbl" style="margin-top:4px">Verfuegbare Streams (${onlineStreams.length}/${state.serverStreams.length})</div>
                ${onlineStreams.length === 0 ? '<div class="lf-empty">Streams werden geprueft…</div>' : `
                  <div class="streams-scroll">
                    ${onlineStreams.map((stream) => {
                      const playing = state.serverAudio.playing && state.serverAudio.url === stream.url;
                      return `
                        <div class="la-row">
                          <div class="la-btn la-flex" style="text-align:left;font-size:11px;color:${playing ? "#34d399" : "#c9d1d9"};background:${playing ? "#16352a" : "#161b22"};border:1px solid ${playing ? "#1f7a5a" : "#21262d"}">
                            ${COUNTRY_FLAGS[stream.country] || "🌍"} ${esc(stream.name)}
                            <span style="color:#4b5563;margin-left:5px">${esc((stream.language || "").toUpperCase())}</span>
                          </div>
                          <div class="la-btn la-radio" style="flex:0 0 auto" onclick="WM2026.${playing ? "stopAudio()" : `playStream('${esc(stream.url)}')`}">${playing ? "⏹" : "▶"}</div>
                        </div>`;
                    }).join("")}
                  </div>`}
              </div>
            </div>
          </div>

          <div class="sbar">
            <div class="sb ${live.length > 0 ? "sb-live" : ""}">
              <div class="sb-v">${live.length || pre.length}</div>
              <div class="sb-l">${live.length > 0 ? "Live" : "Heute"}</div>
            </div>
            <div class="sb"><div class="sb-v">${post.length}</div><div class="sb-l">Fertig</div></div>
            <div class="sb"><div class="sb-v">${totalPlayed}</div><div class="sb-l">Gespielt</div></div>
            <div class="sb"><div class="sb-v">${104 - totalPlayed}</div><div class="sb-l">Offen</div></div>
          </div>

          <div class="scroll">
            ${live.length > 0 ? `<div><div class="sec">🔴 Jetzt live</div>${live.map(renderGameCard).join("")}</div>` : ""}
            ${pre.length > 0 ? `<div><div class="sec">🕐 Heute noch</div>${pre.map(renderGameCard).join("")}</div>` : ""}
            ${post.length > 0 ? `<div><div class="sec">✓ Heute abgeschlossen</div>${post.map(renderGameCard).join("")}</div>` : ""}

            ${todayGames.length === 0 ? `
              <div>
                <div class="empty">
                  <div class="ei">⚽</div>
                  <div class="et">Heute keine Spiele</div>
                  <div class="es">Die WM 2026 startet am<br /><span class="edate">11. Juni 2026</span></div>
                </div>
                ${cd ? `
                  <div class="cdown">
                    <div class="cd"><div class="cd-v">${cd.d}</div><div class="cd-l">Tage</div></div>
                    <div class="cd"><div class="cd-v">${cd.h}</div><div class="cd-l">Std</div></div>
                    <div class="cd"><div class="cd-v">${cd.m}</div><div class="cd-l">Min</div></div>
                  </div>` : ""}
              </div>` : ""}

            <div class="sec">📅 Kompletter Spielplan</div>
            ${days.map(([day, games]) => {
              const isToday = day === todayKey;
              return `
                <div>
                  <div class="day-hdr ${isToday ? "day-today" : ""}">
                    <span>${isToday ? `📅 Heute · ${esc(day)}` : esc(day)}</span>
                    <span class="day-cnt">${games.filter((game) => game.state === "post").length}/${games.length}</span>
                  </div>
                  ${games.map((game) => {
                    const isLive = game.state === "in";
                    const isPost = game.state === "post";
                    const time = game.date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
                    return `
                      <div class="sg ${isLive ? "sg-live" : ""}">
                        <div class="sg-t ${isLive ? "sg-t-live" : isPost ? "sg-t-post" : ""}">${esc(isLive ? game.clock : time)}</div>
                        <div class="sg-flags">
                          ${game.h.logo ? `<img class="sg-flag" src="${esc(game.h.logo)}" alt="" />` : ""}
                          ${game.a.logo ? `<img class="sg-flag" src="${esc(game.a.logo)}" alt="" />` : ""}
                        </div>
                        <div class="sg-info">
                          <div class="sg-match ${isLive ? "sg-match-live" : isPost ? "sg-match-post" : ""}">${esc(game.h.short)} vs ${esc(game.a.short)}</div>
                          <div class="sg-meta">${esc(slugLabel(game.group))}${game.city ? ` · ${esc(game.city)}` : ""}</div>
                        </div>
                        ${isLive || isPost ? `<div class="sg-res ${isLive ? "sg-res-live" : ""}">${esc(game.h.score)}:${esc(game.a.score)}</div>` : '<div class="sg-dash">–</div>'}
                        ${isLive ? '<div class="sg-btn" onclick="WM2026.openMagenta()">▶</div>' : ""}
                      </div>`;
                  }).join("")}
                </div>`;
            }).join("")}

            <div class="comments-wrap ${state.commentsExpanded ? "expanded" : ""}">
              <div class="comments-toggle" onclick="WM2026.toggleCommentsExpand()">
                <span class="lt-l">
                  💬 Kommentare
                  ${state.commentsEnabled === false ? '<span class="lt-badge">AUS</span>' : ""}
                  ${state.serverComments.length > 0 && state.commentsEnabled ? `<span class="lt-badge">${state.serverComments.length}</span>` : ""}
                </span>
                <span class="chev">▾</span>
              </div>
              <div class="comments-panel">
                <div class="live-actions">
                  <div class="la-row">
                    <div class="la-btn la-flex ${state.commentsEnabled ? "la-on" : "la-off"}" onclick="WM2026.toggleComments()">
                      ${state.commentsEnabled ? "💬 Kommentare AN" : "💬 Kommentare AUS"}
                    </div>
                  </div>
                </div>
                <div class="comments-list">
                  ${state.commentsEnabled && state.serverComments.length === 0 ? '<div class="lf-empty" style="padding:0 16px 12px">Noch keine Kommentare geladen. Der Server prueft alle 45 Sekunden.</div>' : ""}
                  ${!state.commentsEnabled ? '<div class="lf-empty" style="padding:0 16px 12px">Kommentare sind deaktiviert. Aktiviere sie oben.</div>' : ""}
                  ${state.commentsEnabled ? state.serverComments.map((comment) => `
                    <div class="comment-item"><b>${esc(comment.source || "kicker")}</b> · ${esc(comment.text || "")}</div>`).join("") : ""}
                </div>
              </div>
            </div>

            <div class="foot">
              <div class="ft">Quelle: <b>ESPN</b> · Widget 3s · API-Cache 30s</div>
              <div class="ft"><b>Server</b> · ${SERVER_URL}</div>
            </div>
          </div>
        </div>
      </div>

      ${renderSidePanel(liveGames, width)}
      ${renderStatusBanner()}
    </div>
  `;
  const _now = document.querySelector(".scroll");
  if (_now) _now.scrollTop = _scrollTop;
}

window.addEventListener("resize", render);

render();
refresh();
setInterval(refresh, 3000);
