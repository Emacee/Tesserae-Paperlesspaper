// agenda_list: the next days as a list. A day per row (name and date in fixed
// columns), all-day events as chips, timed events with their time, a location
// line, and on the right the drive from home with the time to leave.
// The type scales with the number of lines so the list fills the cell.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const PIN = `<svg viewBox="0 0 12 14" aria-hidden="true"><path d="M6 13C6 13 1.5 8.2 1.5 5.3a4.5 4.5 0 019 0C10.5 8.2 6 13 6 13z" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="6" cy="5.3" r="1.6" fill="currentColor"/></svg>`;
const CAR = `<svg viewBox="0 0 18 14" aria-hidden="true"><path d="M2 10V7l1.6-4A1.5 1.5 0 015 2h8a1.5 1.5 0 011.4 1L16 7v3H2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="5" cy="11" r="1.6" fill="currentColor"/><circle cx="13" cy="11" r="1.6" fill="currentColor"/></svg>`;

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const own = data.strings && typeof data.strings === "object" ? data.strings : null;
  const t = (key, fallback) => (own && key in own ? own[key] : ctx?.t ? ctx.t(key, fallback) : fallback ?? key);
  const locale = data.lang || ctx?.locale || "en";
  const h = shadow.host?.clientHeight || ctx?.cell?.h || 500;
  const days = Array.isArray(data.days) ? data.days : [];
  const title = (data.title || "").trim() || t("this_week", "THIS WEEK");

  const dow = (iso) => {
    const [y, m, d] = String(iso).split("-").map(Number);
    return new Intl.DateTimeFormat(locale, { weekday: "short" }).format(new Date(y, m - 1, d)).replace(".", "");
  };
  const range = days.length
    ? `${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(new Date(...days[0].date.split("-").map((v, i) => (i === 1 ? v - 1 : +v))))} → ${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(new Date(...days[days.length - 1].date.split("-").map((v, i) => (i === 1 ? v - 1 : +v))))}`
    : "";

  // lines the list needs, to size the type to the cell
  let lines = 0;
  for (const d of days) {
    const allDay = d.all_day?.length ? 1 : 0;
    const evs = (d.events || []).reduce((n, e) => n + 1 + (e.location ? 0.85 : 0), 0);
    lines += Math.max(1, allDay + evs) + 0.5;
  }
  const fs = Math.max(11, Math.min(24, (h - 70) / Math.max(lines, 1) / 1.45));

  const style = `
    :host { display: block; }
    .al { box-sizing: border-box; height: 100%; display: flex; flex-direction: column; overflow: hidden;
      padding: var(--space-3, 14px) var(--space-4, 24px); color: var(--text-primary, #2f2f2c);
      font-family: var(--font-family, Inter, system-ui, sans-serif); font-size: ${fs}px; font-variant-numeric: tabular-nums; }
    .al-head { display: flex; justify-content: space-between; align-items: baseline; flex: none;
      border-bottom: 3px solid var(--accent-1, #b5482a); padding-bottom: .3em; margin-bottom: .2em; }
    .al-title { font-size: 1.35em; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
    .al-range { color: var(--text-muted, #8a877f); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    .al-day { display: flex; gap: .6em; padding: .25em 0 .3em; border-bottom: 1px solid var(--border-subtle, #d6d1c6); }
    .al-day:last-child { border-bottom: 0; }
    .al-dn { flex: none; width: 4.6em; display: flex; gap: .4em; font-weight: 800; text-transform: uppercase; }
    .al-dn b { width: 1.9em; font-weight: 800; } .al-dn i { width: 1.6em; text-align: right; font-style: normal; font-weight: 800; }
    .al-day.is-today .al-dn { color: var(--accent-1, #b5482a); }
    .al-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: .2em; }
    .al-none { color: var(--text-muted, #8a877f); }
    .al-ad { display: flex; align-items: center; gap: .6em; }
    .al-lab { flex: none; width: 5.2em; font-size: .8em; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--text-muted, #8a877f); }
    .al-chip { padding: 0 .55em; font-weight: 700; border-left: 4px solid var(--c, var(--accent-4, #8f5ea0));
      background: color-mix(in oklab, var(--c, var(--accent-4, #8f5ea0)) 28%, var(--surface, #f7f5f0)); }
    .al-ev { display: flex; align-items: flex-start; gap: .6em; }
    .al-t { flex: none; width: 5.2em; font-weight: 700; color: var(--text-muted, #8a877f); padding-top: .05em; }
    .al-main { flex: 1 1 auto; min-width: 0; line-height: 1.25; }
    .al-ttl { font-weight: 700; } .al-end { margin-left: .5em; font-size: .85em; color: var(--text-muted, #8a877f); }
    .al-loc { display: flex; align-items: center; gap: .35em; font-size: .85em; color: var(--text-muted, #8a877f); }
    .al-loc svg { flex: none; width: .9em; height: 1em; }
    .al-loc span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .al-tr { flex: none; text-align: right; line-height: 1.2; color: var(--accent-5, #2157ba); }
    .al-tr div { display: flex; gap: .35em; align-items: center; justify-content: flex-end; font-weight: 800; }
    .al-tr svg { width: 1.3em; height: 1em; }
    .al-tr small { display: block; font-size: .8em; font-weight: 600; color: var(--text-muted, #8a877f); }
    .al-note { flex: none; color: var(--text-muted, #8a877f); font-size: .85em; padding-top: .3em; }
  `;

  const dayHtml = (d) => {
    const parts = [];
    for (const a of d.all_day || []) {
      const thru = a.through ? ` · ${esc(t("through", "through"))} ${esc(dow(a.through))}` : "";
      parts.push(`<div class="al-ad"><span class="al-lab">${esc(t("all_day", "all day"))}</span><span class="al-chip" style="${a.colour ? `--c:${esc(a.colour)}` : ""}">${esc(a.title)}${thru}</span></div>`);
    }
    for (const e of d.events || []) {
      const tr = e.travel
        ? `<div class="al-tr"><div>${CAR}<span>${e.travel.est ? "≈ " : ""}${e.travel.min} ${esc(t("min", "min"))}</span></div><small>${esc(t("leave", "leave"))} ${esc(e.travel.leave)}</small></div>`
        : "";
      parts.push(`<div class="al-ev"><span class="al-t">${esc(e.start)}</span>
        <div class="al-main"><span class="al-ttl">${esc(e.title)}</span><span class="al-end">${esc(t("until", "until"))} ${esc(e.end)}</span>
        ${e.location ? `<div class="al-loc">${PIN}<span>${esc(e.location)}</span></div>` : ""}</div>${tr}</div>`);
    }
    if (!parts.length) parts.push(`<span class="al-none">–</span>`);
    const [, , dd] = d.date.split("-");
    return `<div class="al-day${d.is_today ? " is-today" : ""}"><div class="al-dn"><b>${esc(dow(d.date))}</b><i>${esc(String(+dd))}</i></div><div class="al-body">${parts.join("")}</div></div>`;
  };

  const note = data.travel === "no_core" ? t("no_core", "")
    : data.travel === "unavailable" ? `${t("unavailable", "")}${data.why ? ` (${data.why})` : ""}`
    : data.via === "osrm" || data.via === "mixed" ? t("estimate", "≈ estimated drive, no live traffic") : "";
  shadow.innerHTML = `<style>${style}</style>
    <div class="al" data-widget="agenda_list">
      <div class="al-head"><span class="al-title">${esc(title)}</span><span class="al-range">${esc(range)}</span></div>
      ${data.error ? `<p class="al-none">${esc(data.error)}</p>` : days.map(dayHtml).join("")}
      ${note ? `<div class="al-note">${esc(note)}</div>` : ""}
    </div>`;
}
