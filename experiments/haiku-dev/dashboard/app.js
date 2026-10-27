"use strict";
// Read-only SwarmHarm run dashboard. Polls /api/run; fetches /api/detail on click. No dependencies.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtS = (s) => s == null ? "—" : s < 120 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
const fmtN = (n) => n == null ? "—" : n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e4 ? (n / 1e3).toFixed(1) + "k" : String(n);
const short = (a) => String(a ?? "").replace(/^job-/, "").slice(0, 6);
const TOOL_COLORS = { bash: "--c-bash", search_archive: "--c-search", fetch_archive: "--c-fetch", submit_review: "--c-submit" };
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const toolColor = (name) => css(TOOL_COLORS[name] || "--c-other");

let data = null, selected = null, tab = "lanes";
const actorIndex = () => Object.fromEntries((data?.actors || []).map((a, i) => [a.id, i]));
const actorColor = (id) => css(`--a${(actorIndex()[id] ?? 0) % 4}`);
const actorName = (id) => {
  const a = (data?.actors || []).find((x) => x.id === id);
  return a ? `${short(a.id)}${a.logical_id ? " · " + a.logical_id.replace("agent-0000", "a") : ""}` : short(id);
};

// ---------------------------------------------------------------- tooltip
const tip = $("tip");
function showTip(ev, text) { tip.textContent = text; tip.hidden = false; moveTip(ev); }
function moveTip(ev) {
  const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }
function bindTips(root) {
  root.querySelectorAll("[data-tip]").forEach((el) => {
    el.addEventListener("mouseenter", (e) => showTip(e, el.dataset.tip));
    el.addEventListener("mousemove", moveTip);
    el.addEventListener("mouseleave", hideTip);
  });
}

// ---------------------------------------------------------------- header
function elapsedNow() {
  if (!data) return null;
  if (data.completion?.elapsed_seconds != null) return data.completion.elapsed_seconds;
  if (data.t0) return (Date.now() - Date.parse(data.t0)) / 1000;
  return data.progress?.elapsed_seconds ?? null;
}
function renderHeader() {
  const m = data.meta || {}, p = data.progress || {}, c = data.completion, g = data.gate;
  $("run-name").textContent = `${data.run}/${data.phase_dir}`;
  const status = c ? `finished: ${c.termination ?? "?"}` : (p.phase || "starting");
  const stale = !c && p.updated_at ? (Date.now() - Date.parse(p.updated_at)) / 1000 : 0;
  const reqMax = m.limits?.max_requests;
  const b = [
    `<span class="badge mode">model <b>${esc(m.model ?? data.model ?? "?")}</b></span>`,
    `<span class="badge">effort <b>${esc(m.effort ?? m.reasoning ?? "?")}</b></span>`,
    `<span class="badge ${c ? "" : "warn"}">status <b>${esc(status)}</b></span>`,
    `<span class="badge">elapsed <b id="elapsed">${fmtS(elapsedNow())}</b></span>`,
    `<span class="badge">requests <b>${p.requests_started ?? c?.requests_started ?? "?"}${reqMax ? " / " + reqMax : ""}</b></span>`,
    `<span class="badge">filed checks <b>${data.filed} / ${data.assigned || 8}</b></span>`,
    `<span class="badge">events <b>${data.events}</b></span>`,
    g ? `<span class="badge good">Phase 1 gate passed at <b>${fmtS(g.t ?? g.elapsed_seconds)}</b> (${esc((g.at || "").slice(11, 19))} UTC${g.formation_event != null ? ", event " + esc(typeof g.formation_event === "object" ? JSON.stringify(g.formation_event).slice(0, 40) : g.formation_event) : ""})</span>`
      : `<span class="badge">Phase 1 gate <b>not passed</b></span>`,
  ];
  if (stale > 60) b.push(`<span class="badge bad">progress not updated for ${fmtS(stale)}</span>`);
  for (const a of data.actors) b.push(`<span class="badge"><span class="sw" style="background:${actorColor(a.id)}"></span>${esc(actorName(a.id))}: ${esc(a.status ?? "?")} · ${a.steps ?? 0} steps</span>`);
  $("badges").innerHTML = b.join("");
}

// ---------------------------------------------------------------- swimlanes
function maxTime() {
  let t = 1;
  for (const a of data.actors) for (const it of a.items) t = Math.max(t, it.end ?? it.t ?? 0);
  return t;
}
function renderLanes() {
  const zoom = +$("zoom").value; $("zoom-val").textContent = `${zoom} px/s`;
  const L = 150, R = 30, laneH = 78, top = 26;
  const T = maxTime() + 5, W = L + T * zoom + R, H = top + data.actors.length * laneH + 10;
  const tickEvery = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800].find((s) => s * zoom >= 60) || 3600;
  const x = (t) => L + (t ?? 0) * zoom;
  const parts = [`<svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">`];
  for (let t = 0; t <= T; t += tickEvery) {
    parts.push(`<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top - 6}" y2="${H}"/><text x="${x(t) + 2}" y="14">${fmtS(t)}</text>`);
  }
  data.actors.forEach((a, i) => {
    const y = top + i * laneH, col = actorColor(a.id);
    parts.push(`<line class="grid" x1="0" x2="${W}" y1="${y + laneH}" y2="${y + laneH}"/>`);
    parts.push(`<rect x="4" y="${y + 8}" width="5" height="${laneH - 16}" fill="${col}"/>`);
    parts.push(`<text class="lane-label" x="14" y="${y + 22}">${esc(short(a.id))}</text>`);
    parts.push(`<text x="14" y="${y + 38}">${esc(a.logical_id || "")}</text><text x="14" y="${y + 52}">${esc(a.batch_id || "")}</text>`);
    a.items.forEach((it, k) => {
      const key = `${a.id}|${it.step}|${it.kind}|${k}`;
      const sel = selected === key ? " sel" : "";
      const common = `class="mark${sel}" data-key="${esc(key)}" data-actor="${esc(a.id)}" data-k="${k}"`;
      if (it.kind === "response") {
        const x0 = x(it.start), w = Math.max(2, (it.end - it.start) * zoom);
        const tip = `model response · step ${it.step}\n${fmtS(it.start)} → ${fmtS(it.end)} · stop ${it.stop}\ntokens in ${it.tokens.input} / out ${it.tokens.output} / cache r ${it.tokens.cache_read} w ${it.tokens.cache_write}\ncalls: ${it.calls.join(", ") || "none"}${it.text ? "\n\n" + it.text : ""}${it.reasoning ? "\n\n[reasoning] " + it.reasoning : ""}`;
        parts.push(`<rect ${common} x="${x0}" y="${y + 8}" width="${w}" height="10" rx="2" fill="${it.text ? col : css("--c-resp")}" data-tip="${esc(tip)}"/>`);
      } else if (it.kind === "tool") {
        const cx = x(it.t), cy = y + 34;
        const tip = `${it.name} · step ${it.step} · event ${it.event_id} · ${fmtS(it.t)} · status ${it.status ?? "?"}\nargs: ${it.args}\nresult: ${it.result}${it.writes.length ? "\nWRITES: " + it.writes.join(", ") : ""}${it.reads.length ? "\nEXACT READS: " + it.reads.join(", ") : ""}`;
        const fail = it.status != null && it.status >= 400;
        parts.push(`<circle ${common} cx="${cx}" cy="${cy}" r="${it.name === "submit_review" ? 7 : 5}" fill="${toolColor(it.name)}" ${fail ? `stroke="${css("--critical")}" stroke-width="2"` : ""} data-tip="${esc(tip)}"/>`);
        if (it.writes.length) parts.push(`<rect x="${cx - 4}" y="${cy + 9}" width="8" height="8" fill="none" stroke="${col}" stroke-width="2" pointer-events="none"/>`);
        if (it.reads.length) parts.push(`<text x="${cx - 3}" y="${cy - 9}" style="fill:${col};font-weight:700" pointer-events="none">R</text>`);
      } else if (it.kind === "platform") {
        const cx = x(it.t), cy = y + 58;
        parts.push(`<path ${common} d="M${cx - 6},${cy + 5} L${cx + 6},${cy + 5} L${cx},${cy - 6} Z" fill="${css("--c-platform")}" data-tip="${esc(`platform update · step ${it.step} · ${fmtS(it.t)}\n${it.text}\n${JSON.stringify(it.data)}`)}"/>`);
      } else if (it.kind === "final") {
        const cx = x(it.t), cy = y + 68;
        const cs = it.completion_state || {};
        parts.push(`<path ${common} d="M${cx},${cy - 7} L${cx + 7},${cy} L${cx},${cy + 7} L${cx - 7},${cy} Z" fill="${css("--c-final")}" data-tip="${esc(`final answer · step ${it.step} · ${fmtS(it.t)}\ncomplete: ${cs.complete} · own ${cs.submitted_reviews}/${cs.assigned_reviews} · swarm ${cs.campaign_submitted_reviews}/${cs.campaign_assigned_reviews}\n\n${it.text}`)}"/>`);
      }
    });
  });
  if (data.gate?.t != null) {
    parts.push(`<line x1="${x(data.gate.t)}" x2="${x(data.gate.t)}" y1="${top - 6}" y2="${H}" stroke="${css("--good-text")}" stroke-dasharray="4 3" stroke-width="2"/><text x="${x(data.gate.t) + 3}" y="${top - 2}" style="fill:${css("--good-text")}">gate</text>`);
  }
  parts.push("</svg>");
  const wrap = $("lanes"), sl = wrap.scrollLeft;
  wrap.innerHTML = parts.join("");
  wrap.scrollLeft = sl;
  bindTips(wrap);
  wrap.querySelectorAll(".mark").forEach((el) => el.addEventListener("click", () => {
    selected = el.dataset.key;
    const a = data.actors.find((x) => x.id === el.dataset.actor);
    showDetail(a, a.items[+el.dataset.k]);
    renderLanes();
  }));
  $("legend").innerHTML = [["bash", "--c-bash"], ["search_archive", "--c-search"], ["fetch_archive", "--c-fetch"], ["submit_review", "--c-submit"],
    ["response (bar; coloured = visible text)", "--c-resp"], ["platform update ▲", "--c-platform"], ["final answer ◆", "--c-final"]]
    .map(([n, v]) => `<span><span class="sw" style="background:${css(v)}"></span>${esc(n)}</span>`).join("") +
    `<span>□ wrote request/note · R exact read · red ring = error status</span>`;
}

async function showDetail(actor, item) {
  const box = $("detail");
  const head = `<div class="bar-row"><span class="sw" style="background:${actorColor(actor.id)}"></span><b>${esc(actorName(actor.id))}</b><span class="muted">step ${item.step} · ${esc(item.kind)}</span></div>`;
  let extra = "";
  if (item.kind === "final") {
    extra = `<div class="tool-hd">Final answer at ${fmtS(item.t)}</div><pre>${esc(item.text)}</pre><details><summary>completion state</summary><pre>${esc(JSON.stringify(item.completion_state, null, 2))}</pre></details>`;
  }
  box.innerHTML = head + extra + `<div class="muted">loading…</div>`;
  let d;
  try {
    const r = await fetch(`/api/detail?actor=${encodeURIComponent(actor.id)}&step=${item.step}`);
    d = await r.json();
  } catch (e) { box.innerHTML = head + extra + `<div class="error">${esc(e)}</div>`; return; }
  const parts = [head, extra];
  if (d.platform) parts.push(`<div class="tool-hd">Platform update delivered before this step</div><pre>${esc(JSON.stringify(d.platform, null, 2))}</pre>`);
  if (d.response) {
    const r = d.response;
    parts.push(`<div class="tool-hd">Model response</div><div class="muted">${esc(r.start?.slice(11, 23) || "?")} → ${esc(r.end?.slice(11, 23) || "?")} UTC · stop ${esc(r.stop)} · in ${r.tokens.input} / out ${r.tokens.output} / cache r ${r.tokens.cache_read} w ${r.tokens.cache_write}</div>`);
    if (r.reasoning) parts.push(`<details><summary>visible reasoning</summary><pre>${esc(r.reasoning)}</pre></details>`);
    parts.push(r.text ? `<pre>${esc(r.text)}</pre>` : `<div class="muted">(no visible text; calls: ${esc(r.calls.join(", ") || "none")})</div>`);
  }
  for (const t of d.tools || []) {
    if (!t) continue;
    parts.push(`<div class="tool-hd"><span class="sw" style="background:${toolColor(t.name)}"></span>${esc(t.name)} <span class="muted">event ${t.event_id}</span></div>`);
    const args = t.arguments || {};
    parts.push(`<div class="muted">arguments</div><pre>${esc(typeof args.command === "string" && Object.keys(args).length === 1 ? args.command : JSON.stringify(args, null, 2))}</pre>`);
    const res = t.result || {};
    if (typeof res.stdout === "string" || typeof res.stderr === "string") {
      parts.push(`<div class="muted">result · status ${res.status ?? "?"} · exit ${res.exit_code ?? "?"}</div><pre>${esc(res.stdout || "")}${res.stderr ? "\n[stderr]\n" + esc(res.stderr) : ""}</pre>`);
      const rest = Object.fromEntries(Object.entries(res).filter(([k]) => !["stdout", "stderr", "status", "exit_code"].includes(k)));
      if (Object.keys(rest).length) parts.push(`<pre>${esc(JSON.stringify(rest, null, 2))}</pre>`);
    } else parts.push(`<div class="muted">result</div><pre>${esc(JSON.stringify(res, null, 2))}</pre>`);
  }
  box.innerHTML = parts.join("");
}

// ---------------------------------------------------------------- communication
function renderComm() {
  const comm = data.writes.filter((w) => w.kind === "request" || w.kind === "note");
  const reads = data.reads;
  const cr = reads.filter((r) => r.kind === "request" || r.kind === "note");
  // graph
  const n = data.actors.length, S = 360, c = S / 2, rad = 130;
  const pos = Object.fromEntries(data.actors.map((a, i) => [a.id, [c + rad * Math.cos(-Math.PI / 2 + 2 * Math.PI * i / n), c + rad * Math.sin(-Math.PI / 2 + 2 * Math.PI * i / n)]]));
  const edges = {};
  for (const r of cr) {
    const k = `${r.author}>${r.reader}`;
    (edges[k] ||= { a: r.author, b: r.reader, n: 0, first: r.t, paths: new Set() });
    edges[k].n++; edges[k].paths.add(r.path); edges[k].first = Math.min(edges[k].first, r.t);
  }
  const g = [`<svg width="${S}" height="${S}" xmlns="http://www.w3.org/2000/svg"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${css("--ink-2")}"/></marker></defs>`];
  for (const e of Object.values(edges)) {
    const [x1, y1] = pos[e.a] || [c, c], [x2, y2] = pos[e.b] || [c, c];
    const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, ox = -dy / L * 10, oy = dx / L * 10;
    const sx = x1 + dx / L * 24 + ox, sy = y1 + dy / L * 24 + oy, ex = x2 - dx / L * 26 + ox, ey = y2 - dy / L * 26 + oy;
    const tip = `${actorName(e.a)} → ${actorName(e.b)}\n${e.paths.size} record(s), ${e.n} exact read(s), first at ${fmtS(e.first)}\n${[...e.paths].map((p) => p.split("/").pop()).join("\n")}`;
    g.push(`<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="${actorColor(e.a)}" stroke-width="${Math.min(2 + e.n, 7)}" marker-end="url(#arr)" data-tip="${esc(tip)}" class="mark"/>`);
    g.push(`<text x="${(sx + ex) / 2 + ox}" y="${(sy + ey) / 2 + oy}">${fmtS(e.first)}</text>`);
  }
  for (const a of data.actors) {
    const [px, py] = pos[a.id];
    const wrote = comm.filter((w) => w.author === a.id).length;
    g.push(`<circle cx="${px}" cy="${py}" r="22" fill="${actorColor(a.id)}" data-tip="${esc(`${actorName(a.id)}\n${wrote} request/note write(s)`)}" class="mark"/><text x="${px}" y="${py + 4}" text-anchor="middle" style="fill:#fff;font-weight:700">${esc(short(a.id).slice(0, 4))}</text><text x="${px}" y="${py + 36}" text-anchor="middle">${wrote} written</text>`);
  }
  g.push("</svg>");
  $("graph").innerHTML = Object.keys(edges).length || comm.length ? g.join("") : `<div class="muted">No source requests or notes yet.</div>` + g.join("");
  bindTips($("graph"));

  // reads table (all kinds)
  $("reads").innerHTML = reads.length ? `<table><tr><th class="num">t</th><th>reader</th><th>author</th><th>record</th><th>kind</th><th class="num">event / step</th></tr>${
    reads.map((r) => `<tr><td class="num">${fmtS(r.t)}</td><td><span class="sw" style="background:${actorColor(r.reader)}"></span>${esc(actorName(r.reader))}</td><td><span class="sw" style="background:${actorColor(r.author)}"></span>${esc(actorName(r.author))}</td><td class="mono">${esc(r.path.split("/").pop())} v${r.version ?? "?"}</td><td>${esc(r.kind)}</td><td class="num">${r.event_id} / ${r.step}</td></tr>`).join("")}</table>`
    : `<div class="muted">No exact reads recorded yet.</div>`;

  // records with replies nested by parent_note_path
  const byPath = {};
  for (const w of comm) (byPath[w.path] ||= []).push(w);
  const children = {};
  for (const [p, ws] of Object.entries(byPath)) { const par = ws[ws.length - 1].parent; if (par) (children[par] ||= []).push(p); }
  const roots = Object.keys(byPath).filter((p) => !byPath[p][byPath[p].length - 1].parent || !byPath[byPath[p][byPath[p].length - 1].parent]);
  roots.sort((a, b) => byPath[a][0].t - byPath[b][0].t);
  const card = (p, depth) => {
    const ws = byPath[p], w = ws[ws.length - 1], body = w.body || {};
    const rs = reads.filter((r) => r.path === p);
    const txt = body.note ?? body.state ?? "";
    const html = `<div class="card ${depth ? "reply" : ""}" style="border-left-color:${actorColor(w.author)};margin-left:${depth * 22}px">
      <div class="hd"><span class="kind">${esc(w.kind)}</span><b>${esc(actorName(w.author))}</b><span class="muted">${esc(body.review_id || "")} · written ${ws.map((v) => `v${v.version} at ${fmtS(v.t)} (event ${v.event_id})`).join(", ")}</span></div>
      <div class="mono muted">${esc(p.split("/").pop())}</div>
      ${w.parent ? `<div class="muted">reply to ${esc(w.parent.split("/").pop())}</div>` : ""}
      ${txt ? `<div>${esc(txt)}</div>` : ""}
      <div class="muted">read by: ${rs.length ? rs.map((r) => `<span style="color:${actorColor(r.reader)}">${esc(actorName(r.reader))}</span> at ${fmtS(r.t)} (v${r.version})`).join(", ") : "nobody yet"}</div>
      <details><summary>full body</summary><pre>${esc(JSON.stringify(body, null, 2))}</pre></details></div>`;
    return html + (children[p] || []).sort((a, b) => byPath[a][0].t - byPath[b][0].t).map((q) => card(q, depth + 1)).join("");
  };
  $("records").innerHTML = roots.length ? roots.map((p) => card(p, 0)).join("") : `<div class="muted">No source requests or notes written yet.</div>`;
  const others = {};
  for (const w of data.writes) if (w.kind !== "request" && w.kind !== "note") others[w.kind] = (others[w.kind] || 0) + 1;
  $("records").innerHTML += `<div class="muted">Other shared writes: ${Object.entries(others).map(([k, v]) => `${esc(k)} ${v}`).join(", ") || "none"}</div>`;
}

// ---------------------------------------------------------------- discovery funnel
function renderFunnel() {
  const D = data.discoveries;
  if (!D) { $("funnel").innerHTML = `<div class="card">Discovery funnel: <b>not computed yet</b> (no <span class="mono">discoveries.json</span> in the run directory).</div>`; return; }
  const ms = D.milestones || [], actors = Object.keys(D.actors || {});
  const cell = (v) => v ? `<td class="reached">${fmtS(v.seconds)}<div class="muted">step ${v.step ?? "?"} · ${fmtN(v.cumulative_tokens)} tok · ev ${v.event ?? "?"}</div></td>` : `<td class="none">—</td>`;
  let h = `<div class="muted">t0 ${esc(D.t0 || "?")} · gate ${D.gate ? `${fmtS(D.gate.seconds)} (event ${D.gate.event})` : "not passed"}</div>`;
  h += `<table><tr><th>milestone</th>${actors.map((a) => `<th><span class="sw" style="background:${actorColor(a)}"></span>${esc(actorName(a))}</th>`).join("")}<th>swarm: agents · first · all</th></tr>`;
  for (const m of ms) {
    const s = (D.swarm || {})[m.key] || {};
    h += `<tr><td><b>${esc(m.key)}</b><div class="muted">${esc(m.label || "")}</div></td>${actors.map((a) => cell((D.actors[a] || {})[m.key])).join("")}<td>${s.agents_reached ?? 0}/${actors.length} · ${fmtS(s.first_seconds)} · ${fmtS(s.all_seconds)}</td></tr>`;
  }
  h += "</table>";
  // timeline: milestone rows, actor dots
  const T = Math.max(10, ...actors.flatMap((a) => ms.map((m) => D.actors[a]?.[m.key]?.seconds ?? 0)), D.gate?.seconds ?? 0) * 1.05;
  const L = 200, W = 900, rowH = 22, H = 24 + ms.length * rowH;
  const x = (t) => L + (t / T) * (W - L - 20);
  const p = [`<h3>Milestone timeline</h3><svg width="${W}" style="max-width:100%;height:auto" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`];
  for (let i = 0; i <= 5; i++) { const t = T * i / 5; p.push(`<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="14" y2="${H}"/><text x="${x(t)}" y="11" text-anchor="middle">${fmtS(t)}</text>`); }
  ms.forEach((m, i) => {
    const y = 24 + i * rowH + rowH / 2;
    p.push(`<text x="4" y="${y + 4}">${esc(m.key)}</text><line class="grid" x1="${L}" x2="${W}" y1="${y}" y2="${y}"/>`);
    actors.forEach((a, j) => {
      const v = D.actors[a]?.[m.key];
      if (v) p.push(`<circle class="mark" cx="${x(v.seconds)}" cy="${y + (j - 1.5) * 3}" r="5" fill="${actorColor(a)}" data-tip="${esc(`${actorName(a)} · ${m.key}\n${fmtS(v.seconds)} · step ${v.step} · ${v.cumulative_tokens} tokens · event ${v.event}`)}"/>`);
    });
  });
  if (D.gate) p.push(`<line x1="${x(D.gate.seconds)}" x2="${x(D.gate.seconds)}" y1="14" y2="${H}" stroke="${css("--good-text")}" stroke-dasharray="4 3" stroke-width="2"/>`);
  p.push("</svg>");
  $("funnel").innerHTML = h + p.join("");
  bindTips($("funnel"));
}

// ---------------------------------------------------------------- tokens
function renderTokens() {
  const metric = $("metric").value;
  const val = (pt) => metric === "total" ? pt.total : pt.cum[metric];
  const T = maxTime(), maxV = Math.max(1, ...data.actors.flatMap((a) => a.tokens.map(val)));
  const L = 70, W = 900, H = 300, B = 26;
  const x = (t) => L + (t / T) * (W - L - 20), y = (v) => H - B - (v / maxV) * (H - B - 10);
  const p = [`<svg width="${W}" style="max-width:100%;height:auto" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`];
  for (let i = 0; i <= 4; i++) { const v = maxV * i / 4; p.push(`<line class="grid" x1="${L}" x2="${W - 20}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${fmtN(Math.round(v))}</text>`); }
  for (let i = 0; i <= 5; i++) { const t = T * i / 5; p.push(`<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${fmtS(t)}</text>`); }
  for (const a of data.actors) {
    const pts = [[0, 0], ...a.tokens.map((pt) => [pt.t ?? 0, val(pt)])];
    p.push(`<polyline fill="none" stroke="${actorColor(a.id)}" stroke-width="2" points="${pts.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}"/>`);
    const last = pts[pts.length - 1];
    p.push(`<text x="${Math.min(x(last[0]) + 4, W - 60)}" y="${y(last[1]) - 4}" style="fill:${actorColor(a.id)}">${esc(short(a.id))}</text>`);
    a.tokens.forEach((pt) => p.push(`<circle class="mark" cx="${x(pt.t ?? 0)}" cy="${y(val(pt))}" r="2.5" fill="${actorColor(a.id)}" data-tip="${esc(`${actorName(a.id)} · step ${pt.step} · ${fmtS(pt.t)}\nthis step: in ${pt.input} / out ${pt.output} / cache r ${pt.cache_read} w ${pt.cache_write}\ncumulative total ${pt.total}`)}"/>`));
  }
  p.push("</svg>");
  $("tokchart").innerHTML = p.join("");
  bindTips($("tokchart"));
  const tot = { input: 0, output: 0, cache_read: 0, cache_write: 0 };
  const rows = data.actors.map((a) => { for (const k in tot) tot[k] += a.totals[k]; const s = Object.values(a.totals).reduce((x, y) => x + y, 0);
    return `<tr><td><span class="sw" style="background:${actorColor(a.id)}"></span>${esc(actorName(a.id))}</td><td class="num">${a.tokens.length}</td>${["input", "output", "cache_read", "cache_write"].map((k) => `<td class="num">${a.totals[k].toLocaleString()}</td>`).join("")}<td class="num">${s.toLocaleString()}</td></tr>`; });
  const all = Object.values(tot).reduce((x, y) => x + y, 0);
  $("toktable").innerHTML = `<h3>Totals</h3><table><tr><th>agent</th><th class="num">responses</th><th class="num">uncached input</th><th class="num">output</th><th class="num">cache read</th><th class="num">cache write</th><th class="num">total</th></tr>${rows.join("")}<tr><th>swarm</th><th></th>${["input", "output", "cache_read", "cache_write"].map((k) => `<th class="num">${tot[k].toLocaleString()}</th>`).join("")}<th class="num">${all.toLocaleString()}</th></tr></table>`;
}

// ---------------------------------------------------------------- metadata
function renderMeta() {
  const sec = (t, v) => v == null ? `<h3>${t}</h3><div class="muted">absent</div>` : `<h3>${t}</h3><pre>${esc(typeof v === "string" ? v : JSON.stringify(v, null, 2))}</pre>`;
  const g = data.gate;
  $("meta").innerHTML = sec("Phase 1 gate", g && { ...g, communication_transcript: undefined }) +
    (g?.communication_transcript ? sec("Gate communication transcript", g.communication_transcript) : "") +
    sec("run-meta.json", data.meta) + sec("progress.json", data.progress) + sec("completion.json", data.completion) + sec("summary.json", data.summary);
}

// ---------------------------------------------------------------- main loop
function render() {
  renderHeader();
  if (tab === "lanes") renderLanes();
  if (tab === "comm") renderComm();
  if (tab === "funnel") renderFunnel();
  if (tab === "tokens") renderTokens();
  if (tab === "meta") renderMeta();
}
async function refresh(force) {
  try {
    const r = await fetch("/api/run", { cache: "no-store" });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    $("error").hidden = true;
    const changed = !data || d.version !== data.version;
    data = d;
    if (changed || force) render(); else renderHeader();
    $("refreshed").textContent = `updated ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $("error").hidden = false; $("error").textContent = `load failed: ${e.message || e}`;
  }
}
function setTab(name) {
  tab = name;
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x.dataset.tab === tab));
  document.querySelectorAll("[data-panel]").forEach((p) => p.hidden = p.dataset.panel !== tab);
  history.replaceState(null, "", "#" + tab);
  if (data) render();
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
if (document.querySelector(`#tabs button[data-tab="${location.hash.slice(1)}"]`)) setTab(location.hash.slice(1));
$("zoom").addEventListener("input", () => data && renderLanes());
$("metric").addEventListener("change", () => data && renderTokens());
setInterval(() => { if ($("auto").checked) refresh(false); }, 4000);
setInterval(() => { const e = $("elapsed"); if (e && data && !data.completion) e.textContent = fmtS(elapsedNow()); }, 1000);
refresh(true);
