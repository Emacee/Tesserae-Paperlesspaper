// travel_time: one row per person, the minutes large on the right, a delay
// against normal as a red pill beside them ("+8 min"), or a quiet "normal".
// Sizes follow the cell: the rows share its height, the type scales with them.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const CAR = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 16V12l2-5h10l2 5v4M3 12h18v5H3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="7.5" cy="17.5" r="1.8" fill="currentColor"/><circle cx="16.5" cy="17.5" r="1.8" fill="currentColor"/></svg>`;

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const w = shadow.host?.clientWidth || ctx?.cell?.w || 600;
  const h = shadow.host?.clientHeight || ctx?.cell?.h || 240;
  const title = (data.title || "").trim()
    || (data.direction === "work" ? t("to_work", "Travel time to work") : t("to_home", "Travel time home"));

  const style = `
    :host { display: block; }
    .tt { box-sizing: border-box; height: 100%; display: flex; flex-direction: column;
      padding: var(--space-3, 14px) var(--space-4, 24px); color: var(--text-primary, #2f2f2c);
      font-family: var(--font-family, Inter, system-ui, sans-serif); }
    .tt-head { display: flex; align-items: center; gap: .5em; flex: none;
      font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
    .tt-head svg { width: 1.25em; height: 1.25em; }
    .tt-chip { margin-left: auto; color: var(--text-muted, #8a877f); letter-spacing: .02em; text-transform: none; font-weight: 700; }
    .tt-rows { flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; }
    .tt-row { flex: 1 1 0; display: flex; align-items: center; gap: .7em; min-height: 0; }
    .tt-row + .tt-row { border-top: 1px solid var(--border-subtle, #d6d1c6); }
    .tt-ini { flex: none; border-radius: 50%; display: flex; align-items: center; justify-content: center;
      background: var(--text-primary, #2f2f2c); color: var(--surface, #f7f5f0); font-weight: 800; }
    .tt-who { flex: 1 1 auto; min-width: 0; line-height: 1.2; }
    .tt-name { font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
    .tt-via { color: var(--text-muted, #8a877f); font-weight: 600; white-space: nowrap; display: block; }
    .tt-late { flex: none; padding: .1em .55em; border-radius: 999px; font-weight: 800; white-space: nowrap;
      background: var(--accent-1, #b5482a); color: #fff; }
    .tt-ok { flex: none; color: var(--text-muted, #8a877f); font-weight: 700; }
    .tt-min { flex: none; text-align: right; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .tt-min small { font-size: .42em; letter-spacing: 0; color: var(--text-muted, #8a877f); font-weight: 700; }
    .tt-msg { color: var(--text-muted, #8a877f); margin: auto 0; }
  `;
  const shell = (inner, head = true) => {
    const chip = data.time ? `${data.source ? esc(data.source) + " · " : ""}${esc(data.time)}` : "";
    const headH = Math.max(14, Math.min(22, h * 0.085));
    shadow.innerHTML = `<style>${style}</style>
      <div class="tt" data-widget="travel_time">
        ${head ? `<div class="tt-head" style="font-size:${headH}px">${CAR}<span>${esc(title)}</span>${chip ? `<span class="tt-chip">${chip}</span>` : ""}</div>` : ""}
        ${inner}
      </div>`;
  };

  if (data.error) { shell(`<p class="tt-msg">${esc(data.error)}</p>`); return; }
  if (data.state === "off") { shadow.innerHTML = ""; return; }
  const people = Array.isArray(data.people) ? data.people : [];
  if (data.state === "empty" || !people.length) {
    shell(`<p class="tt-msg">${esc(t("no_people", "Pick the travel-time sensors in the cell's options."))}</p>`);
    return;
  }

  const rowH = (h - Math.min(22, h * 0.085) * 2.4) / people.length;
  const big = Math.max(18, Math.min(64, rowH * 0.55, w * 0.075));
  const name = Math.max(13, Math.min(27, big * 0.5));
  const small = Math.max(11, Math.min(19, big * 0.36));
  const ini = Math.max(22, Math.min(48, rowH * 0.5));
  const narrow = w < 420;
  const unit = t("min", "min");

  const rows = people.map((p) => {
    const late = Number(p.late) > 0
      ? `<span class="tt-late" style="font-size:${small * 1.15}px">+${esc(p.late)} ${esc(unit)}</span>`
      : p.normal != null ? `<span class="tt-ok" style="font-size:${small}px">${esc(t("normal", "normal"))}</span>` : "";
    const via = p.roads && p.roads.length ? `via ${p.roads.map(esc).join(" · ")}` : "";
    const mins = p.min != null
      ? `${esc(p.min)}<small> ${esc(unit)}</small>`
      : `<small>${esc(t("unavailable", "no value"))}</small>`;
    return `<div class="tt-row">
        ${narrow ? "" : `<span class="tt-ini" style="width:${ini}px;height:${ini}px;font-size:${ini * 0.46}px">${esc(p.initial)}</span>`}
        <span class="tt-who"><span class="tt-name" style="font-size:${name}px">${esc(p.name)}</span>${via && !narrow ? `<span class="tt-via" style="font-size:${small}px">${via}</span>` : ""}</span>
        ${late}
        <span class="tt-min" style="font-size:${big}px">${mins}</span>
      </div>`;
  }).join("");
  shell(`<div class="tt-rows">${rows}</div>`);
}
