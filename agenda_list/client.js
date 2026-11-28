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

// Waste bins, as in the Waste widget: the colour of the stream, a small sign on it.
const WASTE_COLOURS = {
  papier: ["--accent-5", "#2157ba"], gft: ["--accent-4", "#22706a"], restafval: ["--text-primary", "#2f2f2c"],
  pmd: ["--accent-2", "#a07a1f"], glas: ["--accent-3", "#5b7f3a"], textiel: ["--accent-6", "#7a4f8f"],
  kerstbomen: ["--accent-3", "#5b7f3a"], tuinafval: ["--accent-3", "#5b7f3a"], grofvuil: ["--text-muted", "#8a877f"],
};
const WASTE_GLYPHS = {
  papier: '<path d="M9.4 12h5.2M9.4 14.4h5.2M9.4 16.8h3.2"/>',
  gft: '<path d="M9.2 17.6c0-3.8 2.4-6.2 5.8-6.2 0 3.8-2.1 6.2-5.8 6.2zM9.2 17.6l3-3"/>',
  pmd: '<path d="M11 11h2v1.4l1 1.2V17.5a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-3.9l1-1.2z"/>',
  glas: '<path d="M11 11h2v1.4l1 1.2V17.5a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-3.9l1-1.2z"/>',
  textiel: '<path d="M9.2 11.8 7.4 13.3l1 1.8 1-.6V18.5h5.2v-4l1 .6 1-1.8-1.8-1.5-1 .6a2 2 0 0 1-3.6 0z"/>',
  kerstbomen: '<path d="M12 10.6 9.4 14.2h1.8L9 17.2h6l-2.2-3h1.8zM12 17.2v1.6"/>',
  tuinafval: '<path d="M9.2 17.6c0-3.8 2.4-6.2 5.8-6.2 0 3.8-2.1 6.2-5.8 6.2zM9.2 17.6l3-3"/>',
};
function wasteColour(type) {
  const [name, fallback] = WASTE_COLOURS[type] || ["--text-primary", "#2f2f2c"];
  return `var(${name}, ${fallback})`;
}
function wasteBin(type, size) {
  const colour = wasteColour(type);
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true" style="flex:none;vertical-align:middle"><path d="M6 8.6h12l-1.2 11a1.6 1.6 0 0 1-1.6 1.4H8.8a1.6 1.6 0 0 1-1.6-1.4z" fill="${colour}"/><path d="M4.6 8.6h14.8V6.4a1 1 0 0 0-1-1H5.6a1 1 0 0 0-1 1z" fill="${colour}"/><path d="M10 5.4V4h4v1.4" fill="none" stroke="${colour}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><g fill="none" stroke="var(--surface, #fff)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${WASTE_GLYPHS[type] || ""}</g></svg>`;
}

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
    .al-lab { flex: none; width: 5.6em; white-space: nowrap; font-size: .8em; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--text-muted, #8a877f); }
    .al-chip { padding: 0 .55em; font-weight: 700; border-left: 4px solid var(--c, var(--accent-4, #8f5ea0));
      background: color-mix(in oklab, var(--c, var(--accent-4, #8f5ea0)) 28%, var(--surface, #f7f5f0)); }
    .al-waste { display: inline-flex; align-items: center; gap: .4em; background: var(--surface-sunken, #eeeae0); }
    .al-ev { display: flex; align-items: flex-start; gap: .6em; }
    .al-t { flex: none; width: 5.6em; font-weight: 700; color: var(--text-muted, #8a877f); padding-top: .05em; }
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
      if (a.waste) {
        const nm = t(a.waste, "") || a.title;
        parts.push(`<div class="al-ad"><span class="al-lab">${esc(t("waste", "waste"))}</span><span class="al-chip al-waste" style="--c:${wasteColour(a.waste)}">${wasteBin(a.waste, Math.round(fs * 1.15))}<span>${esc(nm)}</span></span></div>`);
        continue;
      }
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

  const wasteNote = !data.waste_note ? ""
    : data.waste_note.startsWith("waste_error:") ? data.waste_note.slice(12).trim() : t(data.waste_note, "");
  const note0 = data.travel === "no_core" ? t("no_core", "")
    : data.travel === "unavailable" ? `${t("unavailable", "")}${data.why ? ` (${data.why})` : ""}`
    : data.via === "osrm" || data.via === "mixed" ? t("estimate", "≈ estimated drive, no live traffic") : "";
  const note = [note0, wasteNote].filter(Boolean).join(" · ");
  shadow.innerHTML = `<style>${style}</style>
    <div class="al" data-widget="agenda_list">
      <div class="al-head"><span class="al-title">${esc(title)}</span><span class="al-range">${esc(range)}</span></div>
      ${data.error ? `<p class="al-none">${esc(data.error)}</p>` : days.map(dayHtml).join("")}
      ${note ? `<div class="al-note">${esc(note)}</div>` : ""}
    </div>`;

  // The estimate above only guesses how tall the list comes out. Measure it and
  // size the type so the list fills the cell, however many events the week has.
  const root = shadow.querySelector(".al");
  if (root && root.clientHeight > 0) {
    const cs = getComputedStyle(root);
    const avail = root.clientHeight - parseFloat(cs.paddingTop || "0") - parseFloat(cs.paddingBottom || "0");
    let size = fs;
    for (let i = 0; i < 3; i += 1) {
      const used = Array.from(root.children).reduce((n, el) => n + el.getBoundingClientRect().height, 0);
      if (!(used > 0) || Math.abs(avail - used) / avail < 0.01) break;
      const next = Math.max(11, Math.min(24, size * (avail / used)));
      if (Math.abs(next - size) < 0.1) break;
      size = next;
      root.style.fontSize = `${size}px`;
    }
  }
}
