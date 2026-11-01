// home_batteries: a small ring per battery. The ring fills to the state of
// charge (red under 20%, ochre under 40%, the page's green above), a dark
// tick marks the target, the percentage sits inside; under it the name and
// one or two lines: charging / discharging / resting and the work mode for
// the home battery, range and plug for the car.
//
// Set in the dashboard's own font, varying only size and weight; nothing
// under 600 weight below 18 px, for e-paper. Icons are drawn here in 2 px
// strokes, the width an e-paper panel keeps sharp.

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const INK = "var(--text-primary, #2f2f2c)";
const PATHS = {
  house: '<path d="M3 11.5 12 4l9 7.5M5.5 9.8V20h13V9.8"/><path d="M10 20v-5h4v5"/>',
  car: '<path d="M5 16v-4l2-5h10l2 5v4M3 12h18v5H3z"/><circle cx="7.5" cy="17.5" r="1.6" fill="currentColor"/><circle cx="16.5" cy="17.5" r="1.6" fill="currentColor"/>',
  bolt: '<path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z" fill="currentColor" stroke="none"/>',
  plug: '<path d="M9 3v5M15 3v5M7 8h10v3.5a5 5 0 0 1-10 0z"/><path d="M12 16.5V21"/>',
  down: '<path d="M12 4v15M6 13l6 6 6-6"/>',
  up: '<path d="M12 20V5M6 11l6-6 6 6"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  road: '<path d="M8 21.5 10.5 2.5M16 21.5 13.5 2.5"/><path d="M12 6v2M12 11v2M12 16v2"/>',
  noexport: '<path d="M4 12h11M11 8l4 4-4 4"/><path d="M19 5v14"/>',
  export: '<path d="M4 12h14M14 8l4 4-4 4"/>',
};
export function icon(name, size, color = "currentColor", sw = 2.2) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" style="flex:none;vertical-align:middle;color:${color}" aria-hidden="true">${PATHS[name] || ""}</svg>`;
}

function fillOf(soc, cs) {
  const v = (n, f) => (cs && cs.getPropertyValue(n).trim()) || f;
  return soc < 20 ? v("--accent-1", "#b5482a") : soc < 40 ? v("--accent-2", "#a07a1f") : v("--accent-4", "#22706a");
}

function ring(size, soc, target, color, sw) {
  const r = size / 2 - sw / 2 - 6;
  const c = 2 * Math.PI * r;
  const cx = size / 2;
  let tick = "";
  if (target != null) {
    const a = ((-90 + 3.6 * target) * Math.PI) / 180;
    const p = (rr) => [cx + rr * Math.cos(a), cx + rr * Math.sin(a)];
    const [x1, y1] = p(r - sw / 2 - 4), [x2, y2] = p(r + sw / 2 + 4);
    tick = `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${INK}" stroke-width="4" stroke-linecap="round"/>`;
  }
  const fill = soc == null ? "" : `<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-dasharray="${((c * soc) / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${cx} ${cx})"/>`;
  return `<svg width="${size}" height="${size}" aria-hidden="true"><circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="var(--surface-sunken, #e6e2d9)" stroke-width="${sw}"/>${fill}${tick}</svg>`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const own = data.strings && typeof data.strings === "object" ? data.strings : null;
  const t = (key, fallback) => (own && key in own ? own[key] : ctx?.t ? ctx.t(key, fallback) : fallback ?? key);
  const w = shadow.host?.clientWidth || ctx?.cell?.w || 440;
  const h = shadow.host?.clientHeight || ctx?.cell?.h || 270;
  const cs = shadow.host && typeof getComputedStyle !== "undefined" ? getComputedStyle(shadow.host) : null;
  const style = `
    :host { display: block; }
    .hb { box-sizing: border-box; height: 100%; display: flex; align-items: center; justify-content: space-around;
      color: var(--text-primary, #2f2f2c); font-family: var(--font-family, Inter, system-ui, sans-serif); font-variant-numeric: tabular-nums; }
    .hb-tile { display: flex; flex-direction: column; align-items: center; text-align: center; min-width: 0; }
    .hb-ring { position: relative; }
    .hb-in { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1; }
    .hb-pct { font-weight: 800; letter-spacing: -.03em; }
    .hb-pct small { font-size: .48em; letter-spacing: 0; }
    .hb-tgt { font-weight: 700; color: var(--text-muted, #8a877f); margin-top: .25em; }
    .hb-name { display: inline-flex; align-items: center; gap: .35em; font-weight: 800; margin-top: .45em; white-space: nowrap; }
    .hb-line { font-weight: 700; white-space: nowrap; margin-top: .25em; display: inline-flex; align-items: center; gap: .3em; }
    .hb-chip { display: inline-flex; align-items: center; gap: .35em; border: 1.5px solid currentColor; border-radius: 999px; padding: .05em .65em .05em .45em; font-weight: 800; white-space: nowrap; }
    .hb-msg { color: var(--text-muted, #8a877f); font-weight: 600; padding: 16px; }
  `;
  const tiles = Array.isArray(data.tiles) ? data.tiles : [];
  if (data.error || !tiles.length) {
    shadow.innerHTML = `<style>${style}</style><div class="hb"><p class="hb-msg">${esc(data.error || t("no_entities", "Pick the batteries in the cell's options."))}</p></div>`;
    return;
  }
  const tw = w / tiles.length;
  const size = Math.max(90, Math.min(tw * 0.62, h - 120, 170));
  const s = size / 140; // type scales with the ring
  const sw = Math.max(9, Math.round(13 * s));
  const red = cs?.getPropertyValue("--accent-1").trim() || "#b5482a";
  const green = cs?.getPropertyValue("--accent-4").trim() || "#22706a";
  const STATE = {
    charging: [t("charging", "Charging"), "up", green],
    discharging: [t("discharging", "Discharging"), "down", red],
    idle: [t("idle", "Idle"), "pause", "var(--text-muted, #8a877f)"],
  };
  const MODE = {
    export_first: [t("mode_export_first", "Export First"), "export"],
    zero_ct: [t("mode_zero_ct", "Zero Export to CT"), "noexport"],
    zero_load: [t("mode_zero_load", "Zero Export to Load"), "noexport"],
  };
  const fs = (n) => `${Math.round(Math.max(13, n * s))}px`;
  const html = tiles.map((tile) => {
    const pct = tile.soc == null ? "–" : tile.soc;
    const lines = [];
    if (tile.kind === "home") {
      const st = STATE[tile.state];
      if (st) lines.push(`<span class="hb-line" style="font-size:${fs(17)};color:${st[2]}">${icon(st[1], Math.round(19 * s), st[2], 2.8)}${esc(st[0])}</span>`);
      const md = MODE[tile.mode];
      if (md) lines.push(`<span class="hb-chip" style="font-size:${fs(14)};margin-top:.4em">${icon(md[1], Math.round(16 * s))}${esc(md[0])}</span>`);
    } else {
      if (tile.km != null) lines.push(`<span class="hb-line" style="font-size:${fs(23)};font-weight:800">${icon("road", Math.round(22 * s))}${esc(tile.km)} km</span>`);
      const plug = tile.charging ? `<span class="hb-line" style="font-size:${fs(16)};color:${green}">${icon("bolt", Math.round(18 * s), green)}${esc(t("car_charging", "charging"))}</span>`
        : tile.plugged ? `<span class="hb-line" style="font-size:${fs(16)}">${icon("plug", Math.round(18 * s))}${esc(t("plugged", "plugged in"))}</span>`
        : tile.plugged === false ? `<span class="hb-line" style="font-size:${fs(16)};color:var(--text-muted, #8a877f)">${esc(t("unplugged", "not plugged in"))}</span>` : "";
      if (plug) lines.push(plug);
    }
    const name = tile.name || (tile.kind === "home" ? t("home_battery", "Home battery") : t("car", "Car"));
    return `<div class="hb-tile" style="width:${tw}px">
      <div class="hb-ring" style="width:${size}px;height:${size}px">${ring(size, tile.soc, tile.target, fillOf(tile.soc ?? 0, cs), sw)}
        <div class="hb-in"><span class="hb-pct" style="font-size:${fs(40)}">${esc(pct)}<small>%</small></span>${tile.target != null ? `<span class="hb-tgt" style="font-size:${fs(13)}">${esc(t("target", "target"))} ${esc(tile.target)}%</span>` : ""}</div></div>
      <span class="hb-name" style="font-size:${fs(19)}">${icon(tile.kind === "home" ? "house" : "car", Math.round(22 * s))}${esc(name)}</span>
      ${lines.join("")}
    </div>`;
  }).join("");
  shadow.innerHTML = `<style>${style}</style><div class="hb" data-widget="home_batteries">${html}</div>`;
}
