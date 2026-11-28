// waste_next: the next waste collection. As a round tile (a ring that fills as
// the day comes closer, the bin inside, its name and the day under it, in the
// style of the home battery rings) or as a short list of the next collections.
// Colours come from the page's theme, flat, for e-paper; icons are drawn here in
// 2 px strokes.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Types some municipalities call differently, folded onto the ones with an icon.
const ALIASES = { papiercont: "papier", papierbak: "papier", gftcont: "gft", plastic: "pmd", plasticafval: "pmd", glascont: "glas" };
const canon = (type) => ALIASES[type] || type;

// Bin colours: the standard container colours, on the colours an e-paper panel has.
const COLOURS = {
  papier: ["--accent-5", "#2157ba"],
  gft: ["--accent-4", "#22706a"],
  restafval: ["--text-primary", "#2f2f2c"],
  pmd: ["--accent-2", "#a07a1f"],
  glas: ["--accent-3", "#5b7f3a"],
  textiel: ["--accent-6", "#7a4f8f"],
  kerstbomen: ["--accent-3", "#5b7f3a"],
  tuinafval: ["--accent-3", "#5b7f3a"],
  grofvuil: ["--text-muted", "#8a877f"],
};
const GLYPHS = {
  papier: '<path d="M9.4 12h5.2M9.4 14.4h5.2M9.4 16.8h3.2"/>',
  gft: '<path d="M9.2 17.6c0-3.8 2.4-6.2 5.8-6.2 0 3.8-2.1 6.2-5.8 6.2zM9.2 17.6l3-3"/>',
  pmd: '<path d="M11 11h2v1.4l1 1.2V17.5a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-3.9l1-1.2z"/>',
  glas: '<path d="M11 11h2v1.4l1 1.2V17.5a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-3.9l1-1.2z"/>',
  textiel: '<path d="M9.2 11.8 7.4 13.3l1 1.8 1-.6V18.5h5.2v-4l1 .6 1-1.8-1.8-1.5-1 .6a2 2 0 0 1-3.6 0z"/>',
  kerstbomen: '<path d="M12 10.6 9.4 14.2h1.8L9 17.2h6l-2.2-3h1.8zM12 17.2v1.6"/>',
  tuinafval: '<path d="M9.2 17.6c0-3.8 2.4-6.2 5.8-6.2 0 3.8-2.1 6.2-5.8 6.2zM9.2 17.6l3-3"/>',
};

function colourOf(type, cs) {
  const [name, fallback] = COLOURS[canon(type)] || ["--text-primary", "#2f2f2c"];
  return (cs && cs.getPropertyValue(name).trim()) || fallback;
}

// A wheelie bin in the colour of its stream, with a small sign on it.
export function bin(type, size, colour) {
  const glyph = GLYPHS[canon(type)] || "";
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true" style="flex:none"><path d="M6 8.6h12l-1.2 11a1.6 1.6 0 0 1-1.6 1.4H8.8a1.6 1.6 0 0 1-1.6-1.4z" fill="${colour}"/><path d="M4.6 8.6h14.8V6.4a1 1 0 0 0-1-1H5.6a1 1 0 0 0-1 1z" fill="${colour}"/><path d="M10 5.4V4h4v1.4" fill="none" stroke="${colour}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><g fill="none" stroke="var(--surface, #fff)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${glyph}</g></svg>`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const own = data.strings && typeof data.strings === "object" ? data.strings : null;
  const t = (key, fallback) => (own && key in own ? own[key] : ctx?.t ? ctx.t(key, fallback) : fallback ?? key);
  const locale = data.lang || ctx?.locale || "en";
  const w = shadow.host?.clientWidth || ctx?.cell?.w || 440;
  const h = shadow.host?.clientHeight || ctx?.cell?.h || 270;
  const cs = shadow.host && typeof getComputedStyle !== "undefined" ? getComputedStyle(shadow.host) : null;
  const v = (n, f) => (cs && cs.getPropertyValue(n).trim()) || f;
  const red = v("--accent-1", "#b5482a");

  const nameOf = (it) => {
    const own = t(canon(it.type), "");
    if (own) return own;
    const n = String(it.name || it.type || "");
    return n.charAt(0).toUpperCase() + n.slice(1);
  };
  const dayWord = (g, short = false) => {
    if (g.days === 0) return t("today", "Today");
    if (g.days === 1) return t("tomorrow", "Tomorrow");
    const [y, m, d] = g.date.split("-").map(Number);
    return new Intl.DateTimeFormat(locale, { weekday: short ? "short" : "long", day: "numeric", month: "short" }).format(new Date(y, m - 1, d)).replace(/^./, (c) => c.toUpperCase());
  };
  const soon = (g) => g.days <= 1;
  const inDays = (g) => (g.days >= 2 ? t("in_days", "in {n} days").replace("{n}", g.days) : "");

  const base = `
    :host { display: block; }
    .wn { box-sizing: border-box; height: 100%; display: flex; flex-direction: column; color: var(--text-primary, #2f2f2c);
      font-family: var(--font-family, Inter, system-ui, sans-serif); overflow: hidden; }
    .wn-msg { margin: auto; padding: 0 var(--space-3, 14px); text-align: center; color: var(--text-muted, #8a877f); }
    .soon { color: ${red}; }
  `;
  const msg = (text, size) => {
    shadow.innerHTML = `<style>${base}</style><div class="wn" data-widget="waste_next"><p class="wn-msg" style="font-size:${size}px">${esc(text)}</p></div>`;
  };
  const small = Math.max(13, Math.min(18, h * 0.07, w * 0.05));
  if (data.error) { msg(data.error, small); return; }
  if (data.state === "setup") { msg(t("setup", "Enter your postcode and house number in the settings."), small); return; }
  const groups = Array.isArray(data.groups) ? data.groups : [];
  if (!groups.length) { msg(t("nothing", "No collection days found"), small); return; }

  if (data.display === "list") {
    const title = (data.title || "").trim() || t("title", "Waste");
    const rows = groups.length;
    const fs = Math.max(12, Math.min(24, (h - 46) / rows / 2.7, w * 0.05));
    const icon = Math.round(fs * 1.9);
    const html = groups.map((g) => {
      const icons = g.items.slice(0, 3).map((it) => bin(it.type, icon, colourOf(it.type, cs))).join("");
      const names = g.items.map(nameOf).join(" + ");
      return `<div class="row"><span class="ic">${icons}</span>
        <span class="who"><b>${esc(names)}</b></span>
        <span class="day${soon(g) ? " soon" : ""}">${esc(dayWord(g, true))}<i>${esc(inDays(g))}</i></span></div>`;
    }).join("");
    shadow.innerHTML = `<style>${base}
      .wn { padding: var(--space-3, 14px) var(--space-4, 24px); font-size: ${fs}px; }
      .hd { flex: none; font-size: ${Math.max(13, fs * 0.8)}px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
        border-bottom: 3px solid var(--accent-1, #b5482a); padding-bottom: .25em; margin-bottom: .2em; }
      .row { flex: 1 1 0; min-height: 0; display: flex; align-items: center; gap: .7em; }
      .row + .row { border-top: 1px solid var(--border-subtle, #d6d1c6); }
      .ic { flex: none; display: flex; gap: .1em; }
      .who { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; line-height: 1.2; }
      .who b { font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .day { flex: none; font-weight: 800; text-align: right; white-space: nowrap; line-height: 1.2; display: flex; flex-direction: column; }
      .day i { font-style: normal; color: var(--text-muted, #8a877f); font-weight: 600; font-size: .75em; }
    </style><div class="wn" data-widget="waste_next"><div class="hd">${esc(title)}</div>${html}</div>`;
    return;
  }

  // The tile: the ring counts down to the collection, the bin(s) inside.
  const g = groups[0];
  const size = Math.max(70, Math.min(w * 0.62, h * 0.6, 190));
  const sw = Math.max(8, size * 0.1);
  const r = size / 2 - sw / 2 - 4;
  const c = 2 * Math.PI * r;
  const frac = 1 - Math.min(g.days, 14) / 14;
  const main = colourOf(g.items[0].type, cs);
  const inner = g.items.length > 1 ? Math.round(size * 0.34) : Math.round(size * 0.56);
  const icons = g.items.slice(0, 2).map((it) => bin(it.type, inner, colourOf(it.type, cs))).join("");
  const names = g.items.map(nameOf).join(" + ");
  const nameFs = Math.max(14, Math.min(26, size * 0.15, w * 0.07));
  const dayFs = Math.max(13, nameFs * 0.85);
  shadow.innerHTML = `<style>${base}
    .wn { align-items: center; justify-content: center; text-align: center; gap: ${Math.max(4, size * 0.04)}px; }
    .ring { position: relative; width: ${size}px; height: ${size}px; flex: none; }
    .ring svg.r { position: absolute; left: 0; top: 0; }
    .in { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 2px; }
    .nm { font-weight: 800; font-size: ${nameFs}px; line-height: 1.15; max-width: 94%; }
    .dy { font-weight: 800; font-size: ${dayFs}px; line-height: 1.2; }
    .in-days { color: var(--text-muted, #8a877f); font-weight: 600; font-size: ${dayFs * 0.85}px; }
  </style><div class="wn" data-widget="waste_next">
    <div class="ring"><svg class="r" width="${size}" height="${size}" aria-hidden="true"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--surface-sunken, #e6e2d9)" stroke-width="${sw}"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${main}" stroke-width="${sw}" stroke-dasharray="${(c * frac).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>
      <div class="in">${icons}</div></div>
    <div class="nm">${esc(names)}</div>
    <div class="dy${soon(g) ? " soon" : ""}">${esc(dayWord(g))}</div>
    ${inDays(g) ? `<div class="in-days">${esc(inDays(g))}</div>` : ""}
  </div>`;
}
