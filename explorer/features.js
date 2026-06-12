/* RL Trajectory Auditor — feature pack
   Daily Specimen + Gauntlet (quiz engine), the Failure Map (canvas scatter of
   all judged runs), Trajectory Diff (fork divergence), and Ask-the-trace
   (BYO-key Gemini chat). Classic script; uses app.js globals. */

const SITE_URL = location.origin + location.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
const DAILY_EPOCH = Date.UTC(2026, 5, 1);            // specimen #1 = 2026-06-01

/* ====================== quiz engine (daily + gauntlet) =================== */
const QZ = { mode: null, ids: [], i: 0, results: [], answered: false };

function _mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function _quizPool() {
  return state.index.filter((c) => !c.local && c.agree === false && c.judge_diagnosis)
    .map((c) => c.trajectory_id).sort();
}

function startDaily() {
  const pool = _quizPool();
  if (!pool.length) return toast("no data yet");
  const n = Math.floor((Date.now() - DAILY_EPOCH) / 86400000) + 1;
  QZ.mode = "daily"; QZ.num = n; QZ.ids = [pool[((n % pool.length) + pool.length) % pool.length]];
  QZ.i = 0; QZ.results = [];
  const st = _dailyState();
  if (st.last === _today() && st.played) {
    _quizShare(st.correct ? [true] : [false], true);   // already played: show card
    return;
  }
  _quizBegin();
}

function startGauntlet() {
  const pool = _quizPool();
  if (pool.length < 10) return toast("no data yet");
  const rng = _mulberry32(42);
  const shuffled = pool.slice();
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1)); [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  QZ.mode = "gauntlet"; QZ.ids = shuffled.slice(0, 10); QZ.i = 0; QZ.results = [];
  _quizBegin();
}

function _quizBegin() {
  hideLanding();
  state.challenge = true; state.guessed = false;
  QZ.answered = false;
  document.body.classList.add("quizzing");
  select(QZ.ids[QZ.i]);
  _quizHud();
}

function _quizHud() {
  let hud = $("#quiz-hud");
  if (!hud) { hud = document.createElement("div"); hud.id = "quiz-hud"; document.body.appendChild(hud); }
  const label = QZ.mode === "daily"
    ? `📅 Daily Specimen #${QZ.num}`
    : `🎯 Gauntlet · trace ${QZ.i + 1} / ${QZ.ids.length}`;
  const score = QZ.results.length ? ` · ${QZ.results.map((r) => (r ? "🟩" : "🟥")).join("")}` : "";
  const next = QZ.answered
    ? (QZ.i < QZ.ids.length - 1
        ? `<button id="qz-next">next trace ›</button>`
        : `<button id="qz-next">see your result ›</button>`)
    : `<span class="qz-tip">step through, then make your call below</span>`;
  hud.innerHTML = `<span class="qz-label">${label}${score}</span>${next}
    <button id="qz-quit" title="leave">×</button>`;
  const nx = $("#qz-next");
  if (nx) nx.onclick = () => {
    if (QZ.i < QZ.ids.length - 1) { QZ.i++; QZ.answered = false; state.guessed = false; select(QZ.ids[QZ.i]); _quizHud(); }
    else _quizShare(QZ.results, false);
  };
  $("#qz-quit").onclick = quitQuiz;
}

function quitQuiz() {
  QZ.mode = null; document.body.classList.remove("quizzing");
  const hud = $("#quiz-hud"); if (hud) hud.remove();
  state.challenge = false; updateChallengeBtn();
  if (state.traj) renderInspector();
}

/* called by makeGuess() in app.js after every challenge guess */
function quizOnGuess(dx, correct) {
  if (!QZ.mode) return;
  QZ.results.push(!!correct);
  QZ.answered = true;
  if (QZ.mode === "daily") {
    const st = _dailyState();
    const yest = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    st.streak = correct ? ((st.last === yest && st.correct) ? (st.streak || 0) + 1 : 1) : 0;
    st.last = _today(); st.played = true; st.correct = !!correct;
    try { localStorage.setItem("rlta_daily", JSON.stringify(st)); } catch (e) {}
  }
  _quizHud();
}

function _today() { return new Date().toISOString().slice(0, 10); }
function _dailyState() {
  try { return JSON.parse(localStorage.getItem("rlta_daily")) || {}; } catch (e) { return {}; }
}

function _quizShare(results, replay) {
  const grid = results.map((r) => (r ? "🟩" : "🟥")).join("");
  const hits = results.filter(Boolean).length;
  let title, share;
  if (QZ.mode === "daily" || replay) {
    const st = _dailyState();
    title = results[0] ? "You matched the judge." : "The judge saw it differently.";
    share = `🔬 RL Specimen #${QZ.num} ${grid}${st.streak ? ` · streak ${st.streak}` : ""}\nCan you out-judge an LLM?\n${SITE_URL}`;
  } else {
    title = hits >= 7 ? `You out-judged Gemini — ${hits}/10.` : hits >= 4 ? `${hits}/10 — judging traces is hard.` : `${hits}/10 — now you see why nobody reads these.`;
    share = `🎯 RL Trajectory Gauntlet ${grid} ${hits}/10\nCan you out-judge an LLM?\n${SITE_URL}`;
  }
  const host = $("#quiz-modal");
  host.innerHTML = `<div class="sc-card qz-card">
    <div class="sc-hd"><h2>${esc(title)}</h2><button class="sc-x" data-close>×</button></div>
    <div class="qz-bd">
      <div class="qz-grid">${grid}</div>
      ${QZ.mode === "daily" || replay ? `<p class="qz-sub">${replay ? "You already played today — come back tomorrow for the next specimen." : "A new specimen drops every day."}</p>` : ""}
      <div class="qz-actions">
        <button id="qz-copy" class="land-go im-go">Copy result</button>
        ${QZ.mode === "daily" || replay ? `<button id="qz-g" class="ghostbtn">try the 10-trace gauntlet →</button>` : `<button id="qz-d" class="ghostbtn">try the daily specimen →</button>`}
      </div>
    </div></div>`;
  openOverlay("#quiz-modal");
  $("#qz-copy").onclick = () => {
    if (navigator.clipboard) navigator.clipboard.writeText(share).then(() => toast("copied — paste it anywhere"));
  };
  const g = $("#qz-g"); if (g) g.onclick = () => { $("#quiz-modal").hidden = true; quitQuiz(); startGauntlet(); };
  const d = $("#qz-d"); if (d) d.onclick = () => { $("#quiz-modal").hidden = true; quitQuiz(); startDaily(); };
  if (!replay) { document.body.classList.remove("quizzing"); const hud = $("#quiz-hud"); if (hud) hud.remove(); QZ.mode = null; state.challenge = false; updateChallengeBtn(); }
}

/* ============================ the failure map ============================ */
let MAP = null;

async function showMap() {
  openOverlay("#map-modal");
  const host = $("#map-modal");
  host.innerHTML = `<div class="sc-card map-card">
    <div class="sc-hd"><h2>The failure map — every judged run</h2><button class="sc-x" data-close>×</button></div>
    <div class="map-legend" id="map-legend"></div>
    <div class="map-wrap"><canvas id="map-canvas"></canvas><div class="map-tip" id="map-tip"></div></div>
    <div class="map-axes"><span>← fewer turns · more turns (log) →</span><span>↑ repetitive (same tool over and over) · varied ↓</span></div>
    <p class="map-note">Each dot is one of the judged runs, colored by the <b>LLM judge's verdict</b>. Ringed dots are in the curated set — click to open the trace.</p>
  </div>`;
  if (!MAP) {
    try { MAP = await fetch("data/map.json").then((r) => r.json()); }
    catch (e) { $("#map-legend").textContent = "map data unavailable"; return; }
  }
  _drawMap();
}

function _vcolor(v) {
  return getComputedStyle(document.documentElement).getPropertyValue("--d-" + (v || "CLEAN")).trim() || "#888";
}

function _drawMap() {
  const cv = $("#map-canvas"); if (!cv) return;
  const wrap = cv.parentElement;
  const W = wrap.clientWidth, H = Math.max(320, Math.min(520, window.innerHeight * 0.5));
  const dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
  const ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
  const pts = MAP.points;
  const xs = pts.map((p) => Math.log2(Math.max(2, p.turns)));
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const pad = 18;
  const px = (x) => pad + ((x - xmin) / (xmax - xmin || 1)) * (W - 2 * pad);
  const py = (r) => pad + (1 - r) * (H - 2 * pad);     // repetitive at top
  MAP.screen = [];
  const counts = {};
  pts.forEach((p, i) => {
    const x = px(xs[i]), y = py(p.rep);
    counts[p.judge] = (counts[p.judge] || 0) + 1;
    ctx.globalAlpha = p.cur ? 0.95 : 0.45;
    ctx.fillStyle = _vcolor(p.judge);
    ctx.beginPath(); ctx.arc(x, y, p.cur ? 4 : 2.4, 0, 7); ctx.fill();
    if (p.cur) { ctx.globalAlpha = 0.9; ctx.strokeStyle = "#1c1714"; ctx.lineWidth = 1; ctx.stroke(); }
    MAP.screen.push({ x, y, p });
  });
  ctx.globalAlpha = 1;
  $("#map-legend").innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1])
    .map(([v, n]) => `<span class="map-key"><i style="background:${_vcolor(v)}"></i>${esc(v)} · ${n.toLocaleString()}</span>`).join("");
  cv.onmousemove = (e) => {
    const r = cv.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    let best = null, bd = 81;
    MAP.screen.forEach((s) => { const d = (s.x - mx) ** 2 + (s.y - my) ** 2; if (d < bd) { bd = d; best = s; } });
    const tip = $("#map-tip");
    if (best) {
      tip.style.display = "block"; tip.style.left = Math.min(best.x + 10, W - 170) + "px"; tip.style.top = (best.y - 8) + "px";
      tip.innerHTML = `<b style="color:${_vcolor(best.p.judge)}">${esc(best.p.judge)}</b> · ${best.p.turns} turns · rep ${Math.round(best.p.rep * 100)}%${best.p.cur ? "<br><span class='dim'>click to open this trace</span>" : ""}`;
      cv.style.cursor = best.p.cur ? "pointer" : "default";
      MAP.hover = best;
    } else { tip.style.display = "none"; MAP.hover = null; cv.style.cursor = "default"; }
  };
  cv.onclick = () => {
    if (MAP.hover && MAP.hover.p.cur) { $("#map-modal").hidden = true; hideLanding(); select(MAP.hover.p.id); }
  };
}

/* ============================ trajectory diff ============================ */
function _toolSeq(traj) {
  const out = [];
  (traj.messages || []).forEach((m) => (m.tools || []).forEach((t) => out.push(t.name)));
  return out;
}

async function showDiff(otherId) {
  const a = state.traj;
  let b = state.localMap[otherId];
  if (!b) {
    const safe = otherId.replace(/[^a-zA-Z0-9_-]/g, "_");
    try { b = await fetch(`data/traj/${safe}.json`).then((r) => r.json()); }
    catch (e) { return toast("couldn't load the other trace"); }
  }
  const sa = _toolSeq(a), sb = _toolSeq(b);
  let L = 0; while (L < sa.length && L < sb.length && sa[L] === sb[L]) L++;
  const chip = (name, cls) => `<span class="df-chip ${cls}">${esc(name)}</span>`;
  const col = (t, seq, side) => {
    const shared = seq.slice(Math.max(0, L - 6), L).map((n) => chip(n, "shared")).join("");
    const div = seq.slice(L, L + 10).map((n, i) => chip(n, side + (i === 0 ? " first" : ""))).join("");
    const more = seq.length > L + 10 ? `<span class="df-more">+${seq.length - L - 10} more</span>` : "";
    return `<div class="df-col"><div class="df-name">${esc(t.task_id)}<small> · ${t.judge && t.judge.diagnosis ? esc(t.judge.diagnosis) : esc(t.heuristic.diagnosis)}</small></div>
      <div class="df-seq">${shared}${div}${more}</div></div>`;
  };
  $("#diff-modal").innerHTML = `<div class="sc-card df-card">
    <div class="sc-hd"><h2>Where the paths split</h2><button class="sc-x" data-close>×</button></div>
    <div class="df-bd">
      <p class="df-sum">These two agents walked the <b>same tool sequence for ${L} call${L === 1 ? "" : "s"}</b>, then diverged. Greyed chips are the shared route; the highlighted chip is each agent's first move after the split.</p>
      <div class="df-cols">${col(a, sa, "mine")}${col(b, sb, "other")}</div>
      <div class="qz-actions"><button id="df-open" class="land-go im-go">open the other trace →</button></div>
    </div></div>`;
  openOverlay("#diff-modal");
  $("#df-open").onclick = () => { $("#diff-modal").hidden = true; select(otherId); };
}

/* ============================ ask the trace ============================== */
function showAsk() {
  const t = state.traj; if (!t) return;
  let key = "";
  try { key = localStorage.getItem("rlta_gem_key") || ""; } catch (e) {}
  $("#ask-modal").innerHTML = `<div class="sc-card ask-card">
    <div class="sc-hd"><h2>Ask this trace</h2><button class="sc-x" data-close>×</button></div>
    <div class="ask-bd">
      <p class="im-p">Interrogate <b>${esc(t.task_id)}</b> with Gemini — <i>your</i> key, called straight from
      your browser (it's stored only in this browser, never sent to us). Get a free key at
      <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com</a>.</p>
      <input id="ask-key" class="ask-key" type="password" placeholder="your Gemini API key (stays in this browser)" value="${esc(key)}" />
      <textarea id="ask-q" class="im-text" placeholder='e.g. "why did the agent loop at the flagged step?" or "was the patch actually wrong?"'></textarea>
      <div class="im-foot"><span class="im-err" id="ask-err"></span><button id="ask-go" class="land-go im-go">Ask →</button></div>
      <div class="ask-a" id="ask-a" hidden></div>
    </div></div>`;
  openOverlay("#ask-modal");
  $("#ask-go").onclick = async () => {
    const k = $("#ask-key").value.trim(), q = $("#ask-q").value.trim();
    if (!k) return ($("#ask-err").textContent = "need a key");
    if (!q) return ($("#ask-err").textContent = "ask something");
    try { localStorage.setItem("rlta_gem_key", k); } catch (e) {}
    $("#ask-err").textContent = ""; $("#ask-go").textContent = "thinking…"; $("#ask-go").disabled = true;
    try {
      const ans = await _askGemini(k, q, t);
      const a = $("#ask-a"); a.hidden = false; a.textContent = ans;
    } catch (e) { $("#ask-err").textContent = "Gemini error: " + e.message; }
    $("#ask-go").textContent = "Ask →"; $("#ask-go").disabled = false;
  };
}

function _traceContext(t) {
  const lines = [`TASK: ${t.task_id} (repo ${t.repo})`,
    `HEURISTIC: ${t.heuristic.diagnosis} / ${t.heuristic.category} — evidence: ${(t.heuristic.evidence || []).join("; ")}`,
    t.judge && t.judge.diagnosis ? `LLM JUDGE: ${t.judge.diagnosis} (${t.judge.reasoning})` : "LLM JUDGE: not run",
    `TEST SPLIT: self=${t.test_split.gen} gold=${t.test_split.gold}`, "", "TRACE:"];
  const msgs = t.messages;
  const pick = msgs.length <= 60 ? msgs : msgs.slice(0, 30).concat(msgs.slice(-30));
  pick.forEach((m) => {
    const tools = (m.tools || []).map((x) => x.name).join(",");
    lines.push(`[${m.idx}] ${m.role}${tools ? " tools:" + tools : ""}: ${(m.content || "").slice(0, 220)}`);
  });
  if (t.patch) lines.push("", "PATCH:", t.patch.slice(0, 2000));
  return lines.join("\n");
}

async function _askGemini(key, q, t) {
  const body = {
    contents: [{ parts: [{ text:
      `You are helping someone understand one RL agent trajectory. Answer the question concisely (3-6 sentences), referencing message indices like [12] where useful.\n\n${_traceContext(t)}\n\nQUESTION: ${q}` }] }],
  };
  const r = await fetch("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": key },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  const txt = j && j.candidates && j.candidates[0] && j.candidates[0].content
    && j.candidates[0].content.parts && j.candidates[0].content.parts[0]
    && j.candidates[0].content.parts[0].text;
  if (!txt) throw new Error("empty response");
  return txt;
}

/* ============================== glossary ================================= */
const GLOSSARY = [
  { h: "The two opinions", rows: [
    ["chip", "HEURISTIC", "Fast, cheap <b>rules</b> — regexes and statistics that scan every run (does the patch edit a test file? did its own tests pass but the real ones fail?). Great at finding <i>suspects</i>, wrong a lot: 57% of its reward-hack flags are false alarms."],
    ["chip", "LLM JUDGE", "Gemini actually <b>reads the whole trace</b> and gives a second opinion with reasoning. Where it disagrees with the heuristic, the judge sides with ground truth ~3 times out of 4. It also writes its own category label in plain words (e.g. <i>“Incorrect implementation or verification”</i>) — read that as its one-line reason."],
  ]},
  { h: "Verdicts — who's to blame for the failure", rows: [
    ["dot:HARNESS", "HARNESS", "The <b>environment</b> broke, not the agent — a missing file, config, or broken test setup. Fix the harness; retraining would be wasted money."],
    ["dot:TRAINING", "TRAINING", "The agent's <b>learned behavior</b> is the problem — it gamed the reward or got stuck in a rut. Fix the reward/rubric or add training coverage."],
    ["dot:PRODUCT", "PRODUCT", "Neither of the above — a routing or policy issue around the agent (or simply unexplained)."],
    ["dot:BOTH", "BOTH", "Two things went wrong at once: a broken environment <i>and</i> bad agent behavior."],
    ["dot:CLEAN", "CLEAN", "Solved properly: both test sets pass, nothing suspicious."],
  ]},
  { h: "Failure categories — what it looked like", rows: [
    ["plain", "Reward Hack", "The run <b>looks</b> successful but earned it by a shortcut — editing the tests, hardcoding the expected answer — instead of fixing the bug. The headline failure mode of RL training."],
    ["plain", "Stuck at Fork", "The agent repeats the <b>same failing move-sequence</b> that other agents also got stuck on (edit, edit, edit…). A shared rut in the training distribution."],
    ["plain", "Context Gap", "The environment never gave the agent something it needed — it was set up to fail."],
    ["plain", "Unclassified / Emergent", "Failed, but no detector could say why. The honest bucket."],
  ]},
  { h: "Scores & badges", rows: [
    ["badge", "self-test 1 / 0", "Did the agent pass <b>its own</b> tests? Gameable — the agent can write or edit these."],
    ["badge", "gold-test 1 / 0", "Did it pass the <b>hidden human-written</b> tests? This is the ground truth. <b>self-test 1 + gold-test 0 = the reward-hack signature.</b>"],
    ["plain", "· 0.90 (confidence)", "How sure that opinion is of its own verdict, from 0 to 1. Self-reported — treat as a hint, not a guarantee."],
    ["mark", "✓ agree / ✗ disagree", "Do the heuristic and the judge give the <b>same verdict</b>? The ✗ disagreements are the interesting traces — that gap is the whole finding."],
    ["plain", "⚑ offending step", "The single message the judge says gives the failure away — the red tick on the minimap."],
    ["plain", "🔁 fork / ⇄ compare", "This run shares its failing move-sequence with N other runs; <b>⇄ compare</b> shows exactly where two of them diverged."],
    ["plain", "⬆ YOURS / LOCAL", "A trajectory you imported. It lives only in this browser tab — never uploaded."],
  ]},
  { h: "Reading the trace — message colors", rows: [
    ["role:system", "system", "The agent's standing instructions — its job and rules."],
    ["role:user", "user", "The task: the bug it was asked to fix."],
    ["role:assistant", "assistant", "The agent's moves — its reasoning and tool calls (⚙)."],
    ["role:tool", "tool", "What the environment said back: file contents, test output, errors."],
  ]},
];

function showGlossary() {
  const sw = (kind, label) => {
    if (kind.startsWith("dot:")) return `<span class="gl-dot" style="background:var(--d-${kind.slice(4)})"></span><b class="gl-term" style="color:var(--d-${kind.slice(4)})">${esc(label)}</b>`;
    if (kind.startsWith("role:")) return `<span class="gl-dot" style="background:var(--r-${kind.slice(5)})"></span><b class="gl-term">${esc(label)}</b>`;
    if (kind === "chip") return `<b class="gl-term gl-chip">${esc(label)}</b>`;
    if (kind === "badge") return `<b class="gl-term gl-badge">${esc(label)}</b>`;
    if (kind === "mark") return `<b class="gl-term">${esc(label)}</b>`;
    return `<b class="gl-term">${esc(label)}</b>`;
  };
  $("#glossary-modal").innerHTML = `<div class="sc-card gl-card">
    <div class="sc-hd"><h2>What everything means</h2><button class="sc-x" data-close>×</button></div>
    <div class="gl-bd">` +
    GLOSSARY.map((sec) =>
      `<h3 class="gl-h">${esc(sec.h)}</h3>` +
      sec.rows.map(([kind, label, def]) =>
        `<div class="gl-row"><span class="gl-l">${sw(kind, label)}</span><span class="gl-d">${def}</span></div>`).join("")
    ).join("") +
    `</div></div>`;
  openOverlay("#glossary-modal");
}

/* ============================== wiring =================================== */
(function wireFeatures() {
  const D = $("#btn-daily"); if (D) D.onclick = startDaily;
  const M = $("#btn-map"); if (M) M.onclick = showMap;
  document.addEventListener("click", (e) => {
    const df = e.target.closest && e.target.closest(".fork-diff");
    if (df) { e.stopPropagation(); showDiff(df.dataset.id); }
    const ga = e.target.closest && e.target.closest("#land-gauntlet");
    if (ga) { e.preventDefault(); startGauntlet(); }
    const ask = e.target.closest && e.target.closest("#b-ask");
    if (ask) showAsk();
    const gl = e.target.closest && e.target.closest(".gl-open");
    if (gl) { e.preventDefault(); showGlossary(); }
  });
  document.addEventListener("keydown", (e) => {
    if ((document.activeElement || {}).tagName === "INPUT") return;
    if (e.key === "g" || e.key === "G") showGlossary();
  });
})();

try { window._rlta = Object.assign(window._rlta || {}, { startDaily, startGauntlet, showMap, showDiff, quizOnGuess }); } catch (e) {}
