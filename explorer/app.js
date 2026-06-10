/* RL Trajectory Auditor — Inspector
   Loads summary.json + index.json, lazy-loads traj/<id>.json, and renders an
   interactive trace inspector: full scroll, step-through playback, minimap,
   teaching annotations, within-trace search + role filter. No framework. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const n2 = (x) => (x == null ? "—" : Number(x).toFixed(2));
const ROLES = ["system", "user", "assistant", "tool"];

const RAIL_FILTERS = [
  { k: "disagree", l: "Disagree" }, { k: "all", l: "All" },
  { k: "Reward Hack", l: "Reward Hack" }, { k: "Context Gap", l: "Context Gap" },
  { k: "Stuck at Fork", l: "Fork" }, { k: "Clean", l: "Clean" },
];

const TEACH = {
  "Reward Hack": "The heuristic flags a <b>reward hack</b> — the agent may have passed its own tests without solving the task (edited a test, hardcoded a value). Read the offending step: did it really game the reward, or is this a false alarm the judge overturns?",
  "Context Gap": "A <b>context gap</b>: the environment didn't give the agent something it needed (a missing file, config, or credential). This is a <b>harness</b> failure — fixing the env beats retraining.",
  "Stuck at Fork": "<b>Stuck at a fork</b>: the agent repeats the same failing maneuver across traces instead of trying the real fix — a training-coverage gap.",
  "Clean": "Looks <b>clean</b>: both the agent's own tests and the gold tests pass, with unremarkable tool use.",
  "_default": "Step through the trace below. Watch the agent's tool calls (gold) and the environment's observations (green); the <b>offending</b> step is marked in red.",
};

const state = {
  summary: null, index: [], view: [], cur: null, traj: null,
  filter: "disagree", q: "",
  cursor: 0, playing: false, timer: null, hidden: new Set(), tq: "",
};

/* ----------------------------------------------------------------------- */
async function boot() {
  try {
    const [summary, index] = await Promise.all([
      fetch("data/summary.json").then((r) => r.json()),
      fetch("data/index.json").then((r) => r.json()),
    ]);
    state.summary = summary;
    state.index = index.cards || [];
    renderTop();
    buildRailFilters();
    applyRailFilter(state.filter);
    if (state.view.length) select(state.view[0].trajectory_id);
  } catch (e) {
    $("#insp").innerHTML = `<div class="empty">No audit data found. Run the export, then reload.</div>`;
  }
}

function renderTop() {
  const s = state.summary, rh = s.reward_hack || {};
  $("#m-h").textContent = n2(rh.heuristic_precision);
  $("#m-j").textContent = n2(rh.judge_precision);
  $("#m-c").textContent = (rh.judge_corrects_pct != null ? rh.judge_corrects_pct + "%" : "—");
  $("#m-n").textContent = (s.n || 0).toLocaleString();
  $("#m-j").parentElement.classList.add("judge");
}

/* ---- left rail --------------------------------------------------------- */
function buildRailFilters() {
  const host = $("#railfilters");
  host.innerHTML = "";
  RAIL_FILTERS.forEach((f) => {
    const b = document.createElement("button");
    b.className = "fchip" + (f.k === state.filter ? " active" : "");
    b.textContent = f.l; b.dataset.k = f.k;
    b.onclick = () => applyRailFilter(f.k);
    host.appendChild(b);
  });
  $("#railsearch").oninput = (e) => { state.q = e.target.value.toLowerCase(); renderRail(); };
}

function applyRailFilter(k) {
  state.filter = k;
  $$(".fchip").forEach((c) => c.classList.toggle("active", c.dataset.k === k));
  renderRail();
}

function passes(c) {
  if (state.q && !((c.task_id + " " + c.repo).toLowerCase().includes(state.q))) return false;
  if (state.filter === "all") return true;
  if (state.filter === "disagree") return c.agree === false;
  return c.heuristic_category === state.filter;
}

function renderRail() {
  state.view = state.index.filter(passes);
  const list = $("#raillist");
  list.innerHTML = "";
  state.view.forEach((c) => {
    const b = document.createElement("button");
    b.className = "tnav" + (state.cur === c.trajectory_id ? " active" : "");
    b.innerHTML =
      `<div class="t-task">${esc(c.task_id)}</div>` +
      `<div class="t-repo">${esc(c.repo || "—")} · ${c.n_messages} msgs</div>` +
      `<div class="t-tags">` +
        `<span class="dot" style="background:var(--d-${esc(c.heuristic_diagnosis)})" title="heuristic"></span>` +
        `<span class="t-vs">vs</span>` +
        `<span class="dot" style="background:var(--d-${esc(c.judge_diagnosis || "CLEAN")})" title="judge"></span>` +
        `<span class="t-mark ${c.agree ? "agr" : "dis"}">${c.agree ? "agree" : "disagree"}</span>` +
      `</div>`;
    b.onclick = () => select(c.trajectory_id);
    list.appendChild(b);
  });
  $("#railcount").textContent = `${state.view.length} of ${state.index.length} trajectories`;
}

/* ---- load + render one trajectory ------------------------------------- */
async function select(id) {
  state.cur = id;
  $$(".tnav").forEach((b) => b.classList.remove("active"));
  renderRail();
  const safe = id.replace(/[^a-zA-Z0-9_-]/g, "_");
  $("#insp").innerHTML = `<div class="empty">loading trace…</div>`;
  try {
    state.traj = await fetch(`data/traj/${safe}.json`).then((r) => r.json());
  } catch (e) {
    $("#insp").innerHTML = `<div class="empty">Could not load this trace.</div>`;
    return;
  }
  // reset interaction state, default cursor = offending (or end)
  stopPlay();
  const off = state.traj.judge.offending_index;
  state.cursor = (Number.isInteger(off) ? off : state.traj.messages.length - 1);
  state.playing = false; state.hidden = new Set(); state.tq = "";
  renderInspector();
}

function chip(who, diag, cat, conf) {
  return `<div class="chipv d-${esc(diag || "CLEAN")}">` +
    `<span class="who">${who}</span>` +
    `<span class="dg">${esc(diag || "—")}</span>` +
    `<span class="ct">${esc(cat || "")}${conf != null ? " · " + n2(conf) : ""}</span></div>`;
}

function renderInspector() {
  const t = state.traj;
  const ts = t.test_split || {};
  const teach = TEACH[t.heuristic.category] || TEACH._default;
  const insp = $("#insp");
  insp.innerHTML = `
    <div class="hd">
      <div class="task">${esc(t.task_id)}</div>
      <div class="sub"><span>repo <b>${esc(t.repo || "—")}</b></span><span>model <b>${esc(t.model || "—")}</b></span><span><b>${t.messages.length}</b> messages</span></div>
      <div class="faceoff">
        ${chip("Heuristic", t.heuristic.diagnosis, t.heuristic.category, t.heuristic.confidence)}
        <span class="vmark ${t.agree ? "agr" : "dis"}">${t.agree ? "✓ agree" : "✗ disagree"}</span>
        ${chip("LLM judge", t.judge.diagnosis, t.judge.category, t.judge.confidence)}
        <div class="ts">
          <span class="tsb ${ts.gen >= 1 && ts.gold < 1 ? "good" : ""}">self-test <b>${ts.gen ?? "—"}</b></span>
          <span class="tsb ${ts.gold < 1 && ts.gen >= 1 ? "bad" : "good"}">gold-test <b>${ts.gold ?? "—"}</b></span>
        </div>
      </div>
      <div class="teach"><span class="icn">✦</span><span class="tx">${teach}</span><button class="x" title="dismiss" onclick="this.parentElement.remove()">×</button></div>
    </div>

    <div class="ctrl">
      <div class="seg">
        <button id="b-step-b" title="step back (←)">‹ step</button>
        <button id="b-play" title="play / pause (space)">▶ play</button>
        <button id="b-step-f" title="step forward (→)">step ›</button>
      </div>
      <button id="b-all" title="reveal whole trace">show all</button>
      <button id="b-off" class="on" title="jump to offending step">⚑ offending</button>
      <div class="rolef">${ROLES.map((r) => `<button class="rf fchip" data-r="${r}">${r}</button>`).join("")}</div>
      <div class="tsearch"><input id="tsearch" type="search" placeholder="search in trace…" autocomplete="off" /></div>
    </div>

    <div class="minimap" id="minimap"></div>
    <div class="console" id="console"></div>

    <div class="readout">
      <div class="blk"><h3>Judge reasoning</h3><p class="reason">${esc(t.judge.reasoning || "—")}</p></div>
      <div class="blk"><h3>Heuristic evidence</h3><ul>${
        (t.heuristic.evidence && t.heuristic.evidence.length)
          ? t.heuristic.evidence.map((e) => `<li>${esc(e)}</li>`).join("")
          : `<li class="none">no heuristic signal</li>`
      }</ul></div>
    </div>`;

  wireControls();
  renderMinimap();
  renderConsole();
  jumpTo(state.cursor, false);
}

/* ---- console rendering ------------------------------------------------- */
function highlight(html) {
  if (!state.tq) return html;
  const re = new RegExp("(" + state.tq.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
  return html.replace(re, "<mark>$1</mark>");
}

function renderDiff(content) {
  return `<div class="diff">` + esc(content).split("\n").map((ln) => {
    let cls = "";
    if (/^\+(?!\+\+)/.test(ln)) cls = "add";
    else if (/^-(?!--)/.test(ln)) cls = "del";
    else if (/^(@@|diff --git|index |---|\+\+\+)/.test(ln)) cls = "hh";
    return `<span class="ln ${cls}">${highlight(ln) || "&nbsp;"}</span>`;
  }).join("") + `</div>`;
}

function bodyHtml(m) {
  const c = m.content || "";
  if (!c.trim() && !(m.tools && m.tools.length)) return `<div class="body empty">(no text)</div>`;
  if (!c.trim()) return "";
  const isDiff = /^diff --git|\n@@ |^@@ /.test(c) || (c.split("\n").filter((l) => /^[+-]/.test(l)).length > 4);
  if (isDiff) return renderDiff(c);
  const long = c.length > 420;
  return `<div class="body ${long ? "clamp" : ""}">${highlight(esc(c))}</div>`;
}

function toolHtml(m) {
  if (!m.tools || !m.tools.length) return "";
  return m.tools.map((tc) => {
    let args = tc.args || "";
    try { args = JSON.stringify(JSON.parse(args), null, 2); } catch (e) {}
    return `<div class="tool"><div class="th"><span class="gear">⚙</span><span class="name">${esc(tc.name)}</span></div>` +
      `<div class="args">${highlight(esc(args))}</div></div>`;
  }).join("");
}

function renderConsole() {
  const t = state.traj, con = $("#console");
  con.innerHTML = t.messages.map((m) => {
    const off = m.offending ? " off" : "";
    return `<div class="turn r-${esc(m.role)}${off}" id="turn-${m.idx}">` +
      `<div class="gutter"><span class="ix">[${m.idx}]</span><span class="role">${esc(m.role)}</span>` +
      (m.offending ? `<span class="off-flag">⚑ offending step</span>` : ``) +
      ((m.content || "").length > 420 ? `<button class="toggle" data-i="${m.idx}">expand</button>` : ``) +
      `</div>` + bodyHtml(m) + toolHtml(m) + `</div>`;
  }).join("");
  con.onclick = (e) => {
    const tg = e.target.closest(".toggle");
    if (tg) { const b = $(`#turn-${tg.dataset.i} .body`); if (b) { b.classList.toggle("clamp"); tg.textContent = b.classList.contains("clamp") ? "expand" : "collapse"; } }
  };
  applyVisibility();
}

function applyVisibility() {
  $$(".turn").forEach((el, i) => {
    const role = (el.className.match(/r-(\w+)/) || [])[1];
    el.classList.toggle("rolehide", state.hidden.has(role));
    el.classList.toggle("future", state.playing && i > state.cursor);
  });
}

/* ---- minimap ----------------------------------------------------------- */
function renderMinimap() {
  const mm = $("#minimap");
  mm.innerHTML = state.traj.messages.map((m) =>
    `<span class="mm r-${esc(m.role)}${m.offending ? " off" : ""}" data-i="${m.idx}" title="[${m.idx}] ${esc(m.role)}"></span>`
  ).join("");
  mm.onclick = (e) => { const t = e.target.closest(".mm"); if (t) jumpTo(+t.dataset.i, true); };
  markCursor();
}
function markCursor() {
  $$(".mm").forEach((el, i) => el.classList.toggle("cursor", i === state.cursor));
}

/* ---- navigation + playback -------------------------------------------- */
function jumpTo(i, setCursor) {
  const n = state.traj.messages.length;
  i = Math.max(0, Math.min(n - 1, i));
  if (setCursor) state.cursor = i;
  markCursor(); applyVisibility();
  const el = $(`#turn-${i}`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}
function step(d) { state.cursor = Math.max(0, Math.min(state.traj.messages.length - 1, state.cursor + d)); jumpTo(state.cursor, false); }
function startPlay() {
  state.playing = true; $("#b-play").textContent = "❚❚ pause"; $("#b-play").classList.add("on");
  applyVisibility();
  state.timer = setInterval(() => {
    if (state.cursor >= state.traj.messages.length - 1) { stopPlay(); return; }
    state.cursor++; jumpTo(state.cursor, false);
  }, 750);
}
function stopPlay() {
  state.playing = false; clearInterval(state.timer); state.timer = null;
  const b = $("#b-play"); if (b) { b.textContent = "▶ play"; b.classList.remove("on"); }
  applyVisibility();
}

function wireControls() {
  $("#b-step-f").onclick = () => { stopPlay(); step(1); };
  $("#b-step-b").onclick = () => { stopPlay(); step(-1); };
  $("#b-play").onclick = () => (state.playing ? stopPlay() : startPlay());
  $("#b-all").onclick = () => { stopPlay(); state.cursor = state.traj.messages.length - 1; applyVisibility(); };
  $("#b-off").onclick = () => {
    const off = state.traj.judge.offending_index;
    if (Number.isInteger(off)) jumpTo(off, true);
  };
  $$(".rf").forEach((b) => b.onclick = () => {
    const r = b.dataset.r;
    if (state.hidden.has(r)) { state.hidden.delete(r); b.classList.remove("active"); }
    else { state.hidden.add(r); b.classList.add("active"); }
    applyVisibility();
  });
  $("#tsearch").oninput = (e) => { state.tq = e.target.value; renderConsole(); };
}

document.addEventListener("keydown", (e) => {
  if (!state.traj) return;
  const tag = (document.activeElement || {}).tagName;
  if (tag === "INPUT") return;
  if (e.key === "ArrowRight") { e.preventDefault(); stopPlay(); step(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); stopPlay(); step(-1); }
  else if (e.key === " ") { e.preventDefault(); state.playing ? stopPlay() : startPlay(); }
});

boot();
