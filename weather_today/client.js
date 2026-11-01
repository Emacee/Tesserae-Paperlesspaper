// weather_today: a column. The weather now on top (icon, temperature, what
// it is like, high / low / rain), the hours of the day below it, one row
// each: hour, icon, temperature, a bar for the rain. Past hours are faded;
// when the rows do not fit, the earliest past ones go first.
//
// The icons are drawn here, in the few inks a colour e-paper panel has:
// a yellow sun, white clouds with a dark outline, blue rain.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const SUN = "var(--wx-sun, #e3b100)";
const RAIN = "var(--wx-rain, #2f63b0)";
const INK = "var(--text-primary, #3d3d3a)";

function sun(cx, cy, r) {
  let rays = "";
  for (let i = 0; i < 8; i++) {
    const a = (i * Math.PI) / 4;
    rays += `<line x1="${(cx + Math.cos(a) * r * 1.45).toFixed(1)}" y1="${(cy + Math.sin(a) * r * 1.45).toFixed(1)}" x2="${(cx + Math.cos(a) * r * 1.9).toFixed(1)}" y2="${(cy + Math.sin(a) * r * 1.9).toFixed(1)}"/>`;
  }
  return `<g stroke="${SUN}" stroke-width="${(r * 0.22).toFixed(1)}" stroke-linecap="round">${rays}</g><circle cx="${cx}" cy="${cy}" r="${r}" fill="${SUN}"/>`;
}
const cloud = (dx = 0, dy = 0, k = 1) =>
  `<path transform="translate(${dx} ${dy}) scale(${k})" d="M24 74 H74 A16 16 0 0 0 72 42 A22 22 0 0 0 30 40 A17 17 0 0 0 24 74Z" fill="#fff" stroke="${INK}" stroke-width="4.5" stroke-linejoin="round"/>`;
const drops = (n, heavy = false) => {
  let s = "";
  for (let i = 0; i < n; i++) s += `<line x1="${(heavy ? 32 : 38) + i * 14}" y1="82" x2="${(heavy ? 27 : 33) + i * 14}" y2="${heavy ? 98 : 95}" stroke="${RAIN}" stroke-width="5" stroke-linecap="round"/>`;
  return s;
};
const moon = (dx, dy, k) => `<path transform="translate(${dx} ${dy}) scale(${k})" d="M38 14 A20 20 0 1 0 60 40 A16 16 0 1 1 38 14Z" fill="${INK}"/>`;
const flakes = () => [34, 50, 66].map((x, i) => `<g transform="translate(${x} ${88 + (i % 2) * 6})" stroke="${RAIN}" stroke-width="3" stroke-linecap="round"><line x1="-5" y1="0" x2="5" y2="0"/><line x1="-2.5" y1="-4.3" x2="2.5" y2="4.3"/><line x1="-2.5" y1="4.3" x2="2.5" y2="-4.3"/></g>`).join("");

const ICONS = {
  sun: () => sun(50, 50, 20),
  moon: () => moon(14, 12, 1.2),
  cloud: () => cloud(0, 4),
  sun_cloud: () => sun(36, 34, 15) + cloud(6, 12, 0.92),
  moon_cloud: () => moon(18, 2, 0.7) + cloud(4, 10, 0.94),
  rain: () => cloud(0, -6) + drops(3),
  heavy_rain: () => cloud(0, -8) + drops(4, true),
  showers: () => sun(36, 30, 14) + cloud(6, 0, 0.92) + drops(3),
  snow: () => cloud(0, -8) + flakes(),
  fog: () => cloud(0, -10) + [80, 90].map((y) => `<line x1="22" y1="${y}" x2="78" y2="${y}" stroke="${INK}" stroke-width="4.5" stroke-linecap="round"/>`).join(""),
  storm: () => cloud(0, -8) + `<path d="M50 70 L40 86 H50 L44 100 L62 80 H52 L58 70Z" fill="${SUN}" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>`,
};
export function iconSvg(name, size) {
  const body = (ICONS[name] || ICONS.cloud)();
  return `<svg width="${size}" height="${size}" viewBox="0 0 100 100" aria-hidden="true">${body}</svg>`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const w = shadow.host?.clientWidth || ctx?.cell?.w || 300;
  const h = shadow.host?.clientHeight || ctx?.cell?.h || 1500;
  const style = `
    :host { display: block; }
    .wt { box-sizing: border-box; height: 100%; position: relative; color: var(--text-primary, #2f2f2c);
      font-family: var(--font-family, Inter, system-ui, sans-serif); font-variant-numeric: tabular-nums; }
    .wt-head { text-align: center; }
    .wt-date { font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
    .wt-place { color: var(--text-muted, #8a877f); font-weight: 700; }
    .wt-temp { font-weight: 800; letter-spacing: -.04em; line-height: 1; }
    .wt-cond { font-weight: 700; line-height: 1.2; }
    .wt-range { font-weight: 700; }
    .wt-hi { color: var(--accent-1, #b5482a); }
    .wt-lo, .wt-mm { color: ${RAIN}; }
    .wt-rule { border-top: 1.5px solid var(--border-subtle, #d6d1c6); }
    .wt-row { display: flex; align-items: center; gap: 6px; font-weight: 700; border-radius: 8px; padding: 0 8px; box-sizing: border-box; }
    .wt-row.now { background: var(--surface-sunken, #ebe7dd); }
    .wt-row.past { opacity: .42; }
    .wt-h { color: var(--text-muted, #8a877f); }
    .wt-t { text-align: right; font-weight: 800; }
    .wt-bar { flex: 1 1 auto; position: relative; height: 12px; margin-left: 8px; }
    .wt-bar span { position: absolute; left: 0; top: 0; height: 100%; border-radius: 3px; background: ${RAIN}; }
    .wt-msg { color: var(--text-muted, #8a877f); padding: 16px; }
  `;
  if (data.error || !data.now) {
    shadow.innerHTML = `<style>${style}</style><div class="wt"><p class="wt-msg">${esc(data.error || t("no_data", "No forecast available."))}</p></div>`;
    return;
  }

  // the head scales with the cell's width; the rows get what is left
  const s = Math.max(0.55, Math.min(1.25, w / 290));
  let date = data.date || "";
  try {
    const d = new Date(`${data.date}T12:00:00`);
    date = new Intl.DateTimeFormat(ctx?.locale || "en", { weekday: "short", day: "numeric", month: "long" }).format(d).replace(".", "");
  } catch (_) { /* the ISO date then */ }
  const unit = data.unit || "°";
  const cond = t(`cond_${data.now.cond}`, data.now.cond);
  const head = `
    <div class="wt-head" style="padding-top:${22 * s}px">
      <div class="wt-date" style="font-size:${19 * s}px">${esc(date)}</div>
      ${data.label ? `<div class="wt-place" style="font-size:${15 * s}px">${esc(data.label)}</div>` : ""}
      <div style="display:flex;justify-content:center;margin-top:${6 * s}px">${iconSvg(data.now.icon, Math.round(140 * s))}</div>
      <div class="wt-temp" style="font-size:${112 * s}px">${esc(data.now.t ?? "–")}${esc(unit)}</div>
      <div class="wt-cond" style="font-size:${23 * s}px;margin:${8 * s}px ${12 * s}px 0">${esc(cond)}</div>
      <div class="wt-range" style="font-size:${21 * s}px;margin-top:${14 * s}px">
        <span class="wt-hi">↑${esc(data.max ?? "–")}°</span> <span class="wt-lo">↓${esc(data.min ?? "–")}°</span>
        · <span class="wt-mm">${esc(String(data.mm ?? 0).replace(".", (ctx?.locale || "en").startsWith("en") ? "." : ","))} ${esc(t("mm", "mm"))}</span>
      </div>
    </div>
    <div class="wt-rule" style="margin:${22 * s}px ${22 * s}px ${12 * s}px"></div>`;
  const headH = (22 + 19 + (data.label ? 18 : 0) + 6 + 140 + 112 + 8 + 28 * (cond.length > 18 * (w / 290) ? 2 : 1) + 14 + 25 + 22 + 12) * s;

  let hours = Array.isArray(data.hours) ? data.hours.slice() : [];
  const avail = h - headH - 12;
  const minRow = 34;
  const fit = Math.max(1, Math.floor(avail / minRow));
  while (hours.length > fit && hours[0]?.past) hours.shift();
  hours = hours.slice(0, fit);
  const rh = Math.min(avail / Math.max(hours.length, 1), 72);
  const fs = Math.max(13, Math.min(21, rh * 0.42, 20 * s));
  const ic = Math.max(20, Math.min(rh - 8, 62));
  const maxMm = Math.max(1.2, ...hours.map((x) => Number(x.mm) || 0));
  const rows = hours.map((x) => `
    <div class="wt-row${x.now ? " now" : ""}${x.past ? " past" : ""}" style="height:${rh - 4}px;margin:0 ${12 * s}px 4px;font-size:${fs}px">
      <span class="wt-h" style="width:${fs * 1.7}px">${String(x.h).padStart(2, "0")}</span>
      ${iconSvg(x.icon, ic)}
      <span class="wt-t" style="width:${fs * 2}px">${esc(x.t ?? "–")}°</span>
      <span class="wt-bar">${Number(x.mm) > 0 ? `<span style="width:${Math.max(4, (100 * Math.min(Number(x.mm), maxMm)) / maxMm)}%"></span>` : ""}</span>
    </div>`).join("");
  shadow.innerHTML = `<style>${style}</style><div class="wt" data-widget="weather_today">${head}<div>${rows}</div></div>`;
}
