/* RL Trajectory Auditor — Explorer
   Loads pre-baked data/summary.json + data/cards.json, renders the dashboard
   and a filterable, keyboard-navigable card stack. No framework, no build. */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
const num2 = (x) => (x == null ? "—" : Number(x).toFixed(2));

const FILTERS = [
  { key: "disagree", label: "Disagreements" },
  { key: "all", label: "All" },
  { key: "Reward Hack", label: "Reward Hack" },
  { key: "Context Gap", label: "Context Gap" },
  { key: "Stuck at Fork", label: "Stuck at Fork" },
  { key: "Clean", label: "Clean" },
];

const state = { cards: [], view: [], i: 0, filter: "disagree" };

async function load() {
  try {
    const [summary, cards] = await Promise.all([
      fetch("data/summary.json").then((r) => r.json()),
      fetch("data/cards.json").then((r) => r.json()),
    ]);
    renderDashboard(summary);
    state.cards = Array.isArray(cards) ? cards : [];
    buildFilters();
    applyFilter(state.filter);
  } catch (e) {
    $("#stage").innerHTML =
      `<div class="empty">No audit data found.<br/><span style="font-size:14px">Run the export, then reload.</span></div>`;
  }
}

function renderDashboard(s) {
  $("#dl-n").textContent = (s.n || 0).toLocaleString();
  const lede = $("#lede");
  const hl = s.headline || "";
  lede.innerHTML = hl.replace(/corrects ~4 of 5 false alarms\.?/i,
    '<span class="drop">corrects ~4 of 5 false alarms.</span>');

  const rh = s.reward_hack || {};
  $("#h-prec").textContent = num2(rh.heuristic_precision);
  $("#j-prec").textContent = num2(rh.judge_precision);
  $("#corrects").textContent = (rh.judge_corrects_pct != null ? rh.judge_corrects_pct + "%" : "—");
  $("#fp").textContent = (rh.false_positives != null ? rh.false_positives.toLocaleString() : "—");

  const ag = s.agreement || {};
  $("#agree-note").textContent =
    `Raw heuristic-vs-judge agreement is ${pct(ag.raw)} (κ = ${num2(ag.kappa)}, n = ${ag.n ?? "—"}). ` +
    `That near-zero κ is a label-space artifact + the over-flagging above — not noise.`;

  const dist = $("#dist");
  dist.innerHTML = "";
  const max = Math.max(1, ...(s.distribution || []).map((d) => d.pct || 0));
  (s.distribution || []).forEach((d) => {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML =
      `<span class="name">${esc(d.label)}</span>` +
      `<span class="track"><span class="fill" style="width:${(d.pct / max) * 100}%"></span></span>` +
      `<span class="pct">${d.pct}%</span>`;
    dist.appendChild(row);
  });
}

function buildFilters() {
  const host = $("#filters");
  host.innerHTML = "";
  FILTERS.forEach((f) => {
    const b = document.createElement("button");
    b.className = "chip" + (f.key === state.filter ? " active" : "");
    b.textContent = f.label;
    b.onclick = () => { applyFilter(f.key); };
    b.dataset.key = f.key;
    host.appendChild(b);
  });
}

function applyFilter(key) {
  state.filter = key;
  document.querySelectorAll(".chip").forEach((c) =>
    c.classList.toggle("active", c.dataset.key === key));
  state.view = state.cards.filter((c) => {
    if (key === "all") return true;
    if (key === "disagree") return c.agree === false;
    return c.heuristic_category === key;
  });
  state.i = 0;
  renderCard();
}

function diagChip(diag, cat, conf) {
  if (!diag) return `<span class="chip-diag" style="opacity:.5">— <span class="cat">not judged</span></span>`;
  return `<span class="chip-diag d-${esc(diag)}">${esc(diag)}` +
    `<span class="cat">${esc(cat || "")}</span>` +
    `<span class="conf">${conf != null ? num2(conf) : ""}</span></span>`;
}

function renderCard() {
  const stage = $("#stage");
  const total = state.view.length;
  $("#counter").textContent = total ? `${state.i + 1} / ${total}` : "0 / 0";
  $("#prev").disabled = state.i <= 0;
  $("#next").disabled = state.i >= total - 1;

  if (!total) {
    stage.innerHTML = `<div class="empty">No trajectories match this filter.</div>`;
    return;
  }
  const c = state.view[state.i];
  const msgs = (c.messages || []).map((m) =>
    `<div class="msg ${m.offending ? "offending" : ""}">` +
    `<span class="ix">[${m.idx}]</span> <span class="role">${esc(m.role)}</span>` +
    `${esc(m.content)}</div>`).join("");
  const evidence = (c.evidence && c.evidence.length)
    ? c.evidence.map((e) => `<li>${esc(e)}</li>`).join("")
    : `<li class="none">no heuristic signal</li>`;
  const ts = c.test_split || {};
  const badge = (label, val, cls) =>
    `<span class="tb ${cls}">${label} <b>${val == null ? "—" : val}</b></span>`;

  stage.innerHTML = `
    <article class="card">
      <div class="head">
        <div class="specimen">Specimen · ${esc(c.trajectory_id)}</div>
        <div class="task">${esc(c.task_id)}</div>
        <div class="meta"><span>repo <b>${esc(c.repo || "—")}</b></span><span>model <b>${esc(c.model || "—")}</b></span></div>
      </div>

      <div class="verdicts">
        <div class="verdict">
          <div class="who">Heuristic says</div>
          ${diagChip(c.heuristic_diagnosis, c.heuristic_category, c.heuristic_confidence)}
        </div>
        <div class="vs">
          <span>vs</span>
          <span class="badge ${c.agree ? "agree" : "disagree"}">${c.agree ? "✓ agree" : "✗ disagree"}</span>
        </div>
        <div class="verdict" style="text-align:right">
          <div class="who">Judge says</div>
          ${diagChip(c.judge_diagnosis, c.judge_category, c.judge_confidence)}
        </div>
      </div>

      <div class="trace">
        <div class="label">Trace · offending message in context</div>
        ${msgs || '<div class="msg none">no message window</div>'}
        <div class="splitbadges">
          ${badge("self-test", ts.gen, ts.gen >= 1 && ts.gold < 1 ? "good" : "")}
          ${badge("gold-test", ts.gold, ts.gold < 1 && ts.gen >= 1 ? "bad" : "good")}
        </div>
      </div>

      <div class="readout">
        <div class="block">
          <h3>Judge reasoning</h3>
          <p class="reasoning">${esc(c.judge_reasoning || "—")}</p>
        </div>
        <div class="block">
          <h3>Heuristic evidence</h3>
          <ul class="evidence">${evidence}</ul>
        </div>
      </div>
    </article>`;
}

function go(d) {
  const n = state.view.length;
  state.i = Math.max(0, Math.min(n - 1, state.i + d));
  renderCard();
}

$("#prev").onclick = () => go(-1);
$("#next").onclick = () => go(1);
document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") go(-1);
  else if (e.key === "ArrowRight") go(1);
});

load();
