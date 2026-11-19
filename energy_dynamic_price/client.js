// energy_dynamic_price, Spectra chart archetype modelled on weather_hourly.
//
// A stepped price curve (one step per 15- or 60-minute slot) with the
// same warm-to-cool gradient language as the hourly temperature chart:
// cheap slots paint in the "primary" accent, expensive ones warm up to
// the "peak" accent. The past is faded so the eye lands on what's still
// to come. The lowest and highest price are marked on the curve and
// repeated in the title chip + legend; the current price is a quiet
// dashed line with a ring, deliberately less loud than the extremes.

import { tokens } from "../../static/spectra-chart.js";

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Same helper as weather_hourly: colour string -> rgba with new alpha.
function withAlpha(color, alpha) {
  if (typeof color !== "string") return color;
  if (color.startsWith("#") && color.length === 7) {
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);
    if (!Number.isNaN(r)) return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const m = color.match(
    /^\s*rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)/
  );
  if (m) return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${alpha})`;
  return color;
}

// Pick an hour step for the x-axis so labels never crowd: fewer ticks on
// narrow cells, and the step always divides the day evenly.
function hourStep(totalHours, cellWidth) {
  const target = cellWidth > 900 ? 12 : cellWidth > 500 ? 8 : cellWidth > 280 ? 5 : 3;
  for (const s of [1, 2, 3, 4, 6, 12, 24]) {
    if (totalHours / s <= target) return s;
  }
  return 24;
}

function addMinutes(hhmm, minutes) {
  const [h, m] = String(hhmm).split(":").map((v) => parseInt(v, 10) || 0);
  const total = (h * 60 + m + minutes) % (24 * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  // the cell's own language, when it names one, before the dashboard's
  const own = data.strings && typeof data.strings === "object" ? data.strings : null;
  const t = (key, fallback) => (own && key in own ? own[key] : ctx?.t ? ctx.t(key, fallback) : fallback ?? key);
  const locale = data.lang || ctx?.locale || "en";
  const css = `<link rel="stylesheet" href="/static/style/spectra-widgets.css">`;
  const bat = data.battery && Array.isArray(data.battery.segments) ? data.battery : null;
  const title = (data.title || "").trim() || (bat ? t("title_battery", "Electricity price & home battery") : t("title", "Electricity price"));

  if (data.error) {
    shadow.innerHTML = `
      ${css}
      <div class="w" data-widget="energy_dynamic_price">
        <div class="w-title"><i class="ph-bold ph-warning-circle"></i><h3>${escapeHtml(title)}</h3></div>
        <div class="w-body"><p class="u-muted">${escapeHtml(data.error)}</p></div>
      </div>`;
    return;
  }

  const slots = Array.isArray(data.slots) ? data.slots : [];
  const prices = slots.map((s) => Number(s.p));
  const n = prices.length;
  const hasData = n >= 2 && prices.every(Number.isFinite);
  const minutes = Number(data.minutes) || 15;
  const unit = data.unit || "ct";
  const decimals = Number(ctx?.cell?.options?.decimals ?? 0) === 1 ? 1 : 0;
  const nf = new Intl.NumberFormat(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const fmt = (v) => (v == null || !Number.isFinite(Number(v)) ? "-" : nf.format(Number(v)));

  const now = data.now || null;
  const lo = data.min || null;
  const hi = data.max || null;
  const dayLabel = (key) => (key === "tomorrow" ? t("tomorrow", "Tomorrow") : t("today", "Today"));
  // "Tomorrow 03:15" when the extreme falls on the next day, bare time otherwise.
  const when = (mark) =>
    mark ? (mark.day === "tomorrow" ? `${dayLabel("tomorrow").toLowerCase()} ${mark.t}` : mark.t) : "";

  const cellWidth = shadow.host?.clientWidth || ctx?.cell?.w || 600;

  const layout = `
    .ep-body { gap: var(--space-2); }
    .ep-chart {
      flex: 1 1 auto;
      min-height: 0;
      position: relative;
    }
    .ep-legend {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-2) var(--space-4);
      align-items: center;
      flex: 0 0 auto;
    }
    .ep-key {
      display: inline-flex;
      align-items: baseline;
      gap: 0.4em;
      font-size: var(--fs-caption);
      font-weight: var(--fw-bold);
      color: var(--text-secondary);
      letter-spacing: var(--ls-label);
    }
    .ep-key .dot {
      align-self: center;
      width: 0.7em;
      height: 0.7em;
      border-radius: 50%;
    }
    .ep-key .dot--lo { background: var(--accent-4); }
    .ep-key .dot--hi { background: var(--accent-1); }
    .ep-key .ring {
      align-self: center;
      width: 0.55em;
      height: 0.55em;
      border-radius: 50%;
      box-shadow: inset 0 0 0 2px var(--text-muted);
    }
    .ep-key b { color: var(--text-primary); font-weight: var(--fw-black); }
    .ep-key .muted { color: var(--text-muted); font-weight: var(--fw-medium); }
    .ep-note { color: var(--text-muted); font-weight: var(--fw-medium); }
    /* now · low / high chip in the title bar, same slot weather_hourly
       uses for now · hi / lo. "now" stays muted on purpose. */
    .ep-range {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: var(--space-2);
      font-size: var(--fs-label);
      font-weight: var(--fw-bold);
      letter-spacing: var(--ls-label);
      color: var(--text-muted);
      white-space: nowrap;
    }
    .ep-range .lo { color: var(--accent-4); }
    .ep-range .hi { color: var(--accent-1); }
    .ep-range .sep { opacity: 0.5; }
    .ep-range i { font-size: 0.85em; }
    /* Narrow (portrait) cells: keep the title readable by dropping the
       "40 NU ·" part of the chip; the legend shows the current price. */
    .ep-bat { --ep-blue: var(--accent-5, #2157ba); }
    .ep-bat .ln { display: inline-block; width: 1.4em; vertical-align: .3em; }
    .ep-bat .ln-soc { border-top: 3px solid var(--ep-blue); }
    .ep-bat .sw {
      display: inline-block;
      width: 1.3em;
      height: .75em;
      vertical-align: -.05em;
      background: color-mix(in srgb, var(--ep-blue) 16%, transparent);
      box-shadow: inset 0 0 0 1.5px var(--ep-blue);
    }
    .ep-legend .grow { flex: 1 1 auto; }
    @container (max-width: 560px) {
      .ep-range .now, .ep-range .now + .sep { display: none; }
    }
    @container (max-width: 280px) {
      .ep-legend { display: none; }
      .ep-range { display: none; }
    }
  `;

  const rangeChip = hasData && (lo || hi)
    ? `
      <span class="ep-range">
        ${now ? `<span class="now">${escapeHtml(fmt(now.p))} ${escapeHtml(t("now_upper", "NOW"))}</span><span class="sep">·</span>` : ""}
        ${lo ? `<span class="lo"><i class="ph-bold ph-arrow-down"></i>${escapeHtml(fmt(lo.p))}</span>` : ""}
        <span class="sep">/</span>
        ${hi ? `<span class="hi"><i class="ph-bold ph-arrow-up"></i>${escapeHtml(fmt(hi.p))}</span>` : ""}
        <span>${escapeHtml(unit)}</span>
      </span>`
    : "";

  // the home battery in the legend: two keys at the end of the one row, what
  // the line is and what the pale bands are. The slot it is in is not shown.
  const hasGrid = bat && bat.segments.some((g) => g.grid);
  const hasSoc = bat && Array.isArray(bat.history) && bat.history.length > 1;
  const batteryKeys = bat && (hasSoc || hasGrid) ? `
        <span class="grow"></span>
        ${hasSoc ? `<span class="ep-key ep-bat"><span class="ln ln-soc"></span>${escapeHtml(t("battery_soc", "Charge level"))}</span>` : ""}
        ${hasGrid ? `<span class="ep-key ep-bat"><span class="sw"></span>${escapeHtml(t("battery_grid", "grid charging"))}</span>` : ""}` : "";

  const showLegend = cellWidth > 440 && hasData;
  // md keeps the legend to one row (low + high); lg adds now, average and
  // the 'tomorrow from ~13:00' hint.
  const wide = cellWidth > 900;
  // Narrow cells drop "now" from the title chip, so the legend carries it.
  const narrow = cellWidth <= 560;
  // Narrow *and* short (e.g. half of a 480x800 portrait frame): low / high
  // already sit in the chip and on the curve, so the legend keeps only
  // "now" and the chart gets the height.
  const cellH = shadow.host?.clientHeight || ctx?.cell?.h || 400;
  const compactLegend = narrow && cellH < 450;
  const pendingNote = data.range !== "today" && !data.has_tomorrow
    ? `<span class="ep-key ep-note"><i class="ph-bold ph-clock"></i>${escapeHtml(t("tomorrow_pending", "Tomorrow's prices from ~13:00"))}</span>`
    : "";
  const legend = showLegend
    ? `
      <div class="ep-legend">
        ${lo && !compactLegend && !bat ? `<span class="ep-key"><span class="dot dot--lo"></span>${escapeHtml(t("lowest", "Lowest"))} <b>${escapeHtml(fmt(lo.p))}</b> ${escapeHtml(unit)} <span class="muted">${escapeHtml(when(lo))}</span></span>` : ""}
        ${hi && !compactLegend && !bat ? `<span class="ep-key"><span class="dot dot--hi"></span>${escapeHtml(t("highest", "Highest"))} <b>${escapeHtml(fmt(hi.p))}</b> ${escapeHtml(unit)} <span class="muted">${escapeHtml(when(hi))}</span></span>` : ""}
        ${(wide || narrow) && !bat && now ? `<span class="ep-key"><span class="ring"></span><span class="muted">${escapeHtml(t("now", "now"))} ${escapeHtml(fmt(now.p))} ${escapeHtml(unit)} · ${escapeHtml(now.from)}–${escapeHtml(now.till)}</span></span>` : ""}
        ${(wide || bat) && data.avg != null ? `<span class="ep-key"><span class="muted">${escapeHtml(t("average", "Average"))} ${escapeHtml(fmt(data.avg))} ${escapeHtml(unit)}</span></span>` : ""}
        ${wide || bat ? pendingNote : ""}${batteryKeys}
      </div>`
    : "";

  const emptyMsg = `<p class="u-muted">${escapeHtml(t("no_data", "No prices available."))}</p>`;

  const frag = ctx?.fragment || "full";
  if (frag === "summary") {
    shadow.innerHTML = `
      ${css}
      <style>.w-body{height:100%;display:flex;align-items:center;justify-content:center}.ep-sum{display:flex;align-items:baseline;gap:var(--space-2);font-weight:var(--fw-bold)}.ep-sum .now{font-size:clamp(2em,26cqmin,6em)}.ep-sum .unit{color:var(--text-muted)}.ep-sum .lo{color:var(--accent-4)}.ep-sum .hi{color:var(--accent-1)}.ep-sum .sep{color:var(--text-muted);opacity:.5}</style>
      <div class="w" data-widget="energy_dynamic_price"><div class="w-body"><span class="ep-sum">
        ${now ? `<span class="now">${escapeHtml(fmt(now.p))}</span><span class="unit">${escapeHtml(unit)}</span>` : ""}
        ${lo && hi ? `<span class="sep">·</span><span class="lo">${escapeHtml(fmt(lo.p))}</span><span class="sep">/</span><span class="hi">${escapeHtml(fmt(hi.p))}</span>` : ""}
      </span></div></div>`;
    return;
  }
  if (frag === "chart") {
    shadow.innerHTML = `
      ${css}
      <style>${layout}.ep-body{padding:var(--space-2)}.ep-chart{flex:1;min-height:0;height:100%;position:relative}</style>
      <div class="w" data-widget="energy_dynamic_price"><div class="w-body ep-body">
        <div class="ep-chart">${hasData ? "<canvas></canvas>" : emptyMsg}</div>
      </div></div>`;
  } else {
    shadow.innerHTML = `
      ${css}
      <style>${layout}</style>
      <div class="w" data-widget="energy_dynamic_price">
        <div class="w-title">
          <i class="ph-bold ph-lightning" style="color:var(--accent-4)"></i>
          <h3>${escapeHtml(title)}</h3>
          ${rangeChip}
        </div>
        <div class="w-body ep-body">
          <div class="ep-chart">${hasData ? "<canvas></canvas>" : emptyMsg}</div>
          ${legend}
        </div>
      </div>`;
  }

  if (!hasData) return;
  const canvas = shadow.querySelector("canvas");
  if (!canvas || !window.Chart) return;
  const tok = tokens(shadow.host);

  // ---- geometry -------------------------------------------------------
  const pMin = Math.min(...prices);
  const pMax = Math.max(...prices);
  const span = Math.max(0.5, pMax - pMin);
  const avg = Number.isFinite(Number(data.avg)) ? Number(data.avg) : (pMin + pMax) / 2;
  const nowIdx = now && Number.isInteger(now.i) ? now.i : null;
  const nowX = nowIdx != null ? nowIdx + Math.min(0.999, Math.max(0, Number(data.now_frac) || 0)) : null;
  const days = Array.isArray(data.days) ? data.days : [];

  // Step points: point i sits at the slot's start, and stepped:"before"
  // carries its value flat to the next slot. One extra point at x=n
  // closes the last slot.
  const pts = prices.map((p, i) => ({ x: i, y: p }));
  pts.push({ x: n, y: prices[n - 1] });

  // ---- colour ---------------------------------------------------------
  // Cheap (≤ average) reads in accent-4, the "primary" teal in the light
  // theme; prices above average warm through accent-2 to accent-1, the
  // "peak" slot. Stops are placed by price, not by chart height, so the
  // colour means the same thing on every cell size.
  function priceGradient(alpha) {
    return (c) => {
      const chart = c.chart;
      const area = chart.chartArea;
      const y = chart.scales?.y;
      if (!area || !y) return withAlpha(tok.accent4, alpha);
      const g = chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
      const h = area.bottom - area.top || 1;
      const pos = (v) => Math.min(1, Math.max(0, (area.bottom - y.getPixelForValue(v)) / h));
      const pAvg = pos(avg);
      const pWarm = Math.max(pAvg, pos(avg + (pMax - avg) * 0.45));
      const pTop = Math.max(pWarm, pos(pMax));
      g.addColorStop(0, withAlpha(tok.accent4, alpha));
      g.addColorStop(pAvg, withAlpha(tok.accent4, alpha));
      g.addColorStop(pWarm, withAlpha(tok.accent2, alpha));
      g.addColorStop(pTop, withAlpha(tok.accent1, alpha));
      g.addColorStop(1, withAlpha(tok.accent1, alpha));
      return g;
    };
  }

  const datasets = [];
  const lineBase = {
    type: "line",
    stepped: "before",
    pointRadius: 0,
    tension: 0,
    fill: "start",
  };
  if (nowIdx != null && nowIdx > 0) {
    // Past: same palette, faded, thinner.
    datasets.push({
      ...lineBase,
      label: "past",
      data: pts.slice(0, nowIdx + 1),
      borderColor: priceGradient(0.4),
      backgroundColor: priceGradient(0.08),
      borderWidth: 2,
      order: 2,
    });
  }
  datasets.push({
    ...lineBase,
    label: "price",
    data: nowIdx != null && nowIdx > 0 ? pts.slice(nowIdx) : pts,
    borderColor: priceGradient(1),
    backgroundColor: priceGradient(0.22),
    borderWidth: 3,
    order: 1,
  });

  // ---- axis -----------------------------------------------------------
  // Canvas text follows the widget's own type scale, so axis labels match
  // the HTML text at any aspect ratio (width-only sizing made them tiny in
  // tall portrait cells). Mirrors --w-font-base = clamp(14px, 7cqmin, 28px)
  // from the cell's virtual (post-zoom) size; computed here rather than
  // read from .w because the shadow-root stylesheet may still be loading.
  const cellHeight = shadow.host?.clientHeight || ctx?.cell?.h || 400;
  const baseFont = Math.min(28, Math.max(14, 0.07 * Math.min(cellWidth, cellHeight)));
  const tickFontSize = Math.max(10, Math.min(22, Math.round(baseFont * 0.72)));
  const markFont = Math.max(11, Math.min(26, Math.round(baseFont * 0.85)));
  const small = cellWidth <= 280;

  const labelAt = (i) => (i < n ? slots[i].t : addMinutes(slots[n - 1].t, minutes));
  const step = hourStep((n * minutes) / 60, cellWidth);
  const tickIdx = [];
  for (let i = 0; i <= n; i++) {
    const [hh, mm] = labelAt(i).split(":").map((v) => parseInt(v, 10));
    if (mm === 0 && hh % step === 0) tickIdx.push(i);
  }

  // ---- overlay plugin: day split, min / max, now ------------------------
  // Reserved bands above the plot: day captions on top, then room for the
  // max label, so neither clips nor collides on short cells.
  const capBand = days.length > 1 && !small ? tickFontSize + 8 : 0;
  const markBand = markFont + 10;

  // ---- the home battery: grid charging as pale bands, today's charge level ----
  const blue = tok.accent5 && /^#|^rgb/.test(tok.accent5) ? tok.accent5 : "#2157ba";
  // behind the prices: the stretches the battery charges from the grid
  function drawBatteryBands(chart, c, family) {
    const x = chart.scales.x;
    const area = chart.chartArea;
    const grid = bat.segments.filter((g) => g.grid);
    if (!grid.length) return;
    const label = t("battery_grid", "grid charging");
    c.save();
    c.font = `700 ${Math.round(tickFontSize * 0.85)}px ${family}`;
    c.textAlign = "center";
    c.textBaseline = "top";
    const labelW = c.measureText(label).width + 8;
    for (const g of grid) {
      const x0 = Math.max(area.left, x.getPixelForValue(g.x0));
      const x1 = Math.min(area.right, x.getPixelForValue(g.x1));
      if (x1 <= x0) continue;
      c.fillStyle = withAlpha(blue, 0.16);
      c.fillRect(x0, area.top, x1 - x0, area.bottom - area.top);
      if (x1 - x0 > labelW) {
        c.fillStyle = blue;
        c.fillText(label, (x0 + x1) / 2, area.top + 6);
      }
    }
    c.restore();
  }
  // in front: today's charge level, one solid line, with the number where it ends
  function drawBattery(chart, c, family) {
    const x = chart.scales.x;
    const area = chart.chartArea;
    const ys = (v) => area.bottom - ((area.bottom - area.top) * Math.max(0, Math.min(100, v))) / 100;
    const px = (v) => x.getPixelForValue(v);
    const hist = Array.isArray(bat.history) ? bat.history : [];
    c.save();
    if (hist.length > 1) {
      c.strokeStyle = blue;
      c.lineWidth = 3;
      c.lineJoin = "round";
      c.setLineDash([]);
      c.beginPath();
      hist.forEach(([hx, hv], k) => (k ? c.lineTo(px(hx), ys(hv)) : c.moveTo(px(hx), ys(hv))));
      c.stroke();
    }
    if (bat.soc != null && Number.isFinite(bat.now_x)) {
      c.font = `800 ${Math.round(tickFontSize * 0.95)}px ${family}`;
      c.fillStyle = blue;
      c.textAlign = "right";
      c.textBaseline = "bottom";
      c.fillText(`${bat.soc}%`, px(bat.now_x) - 8, ys(bat.soc) - 26);
    }
    c.restore();
  }

  const overlay = {
    id: "ep-overlay",
    beforeDatasetsDraw(chart) {
      if (bat) drawBatteryBands(chart, chart.ctx, tok.fontFamily);
    },
    afterDatasetsDraw(chart) {
      const x = chart.scales.x;
      const y = chart.scales.y;
      const area = chart.chartArea;
      const c = chart.ctx;
      const family = tok.fontFamily;
      c.save();
      if (bat) drawBattery(chart, c, family);

      // Day divider + day captions (only when two days are on screen).
      if (days.length > 1) {
        for (let d = 0; d < days.length; d++) {
          const xi = x.getPixelForValue(days[d].i);
          if (d > 0) {
            c.strokeStyle = withAlpha(tok.textMuted, 0.6);
            c.lineWidth = 1.5;
            c.setLineDash([]);
            c.beginPath();
            c.moveTo(xi, area.top - markBand);
            c.lineTo(xi, area.bottom);
            c.stroke();
          }
          if (!small) {
            c.fillStyle = tok.textSecondary;
            c.font = `700 ${tickFontSize}px ${family}`;
            c.textBaseline = "top";
            c.textAlign = "left";
            c.fillText(dayLabel(days[d].key), xi + 6, area.top - markBand - capBand);
          }
        }
      }

      // Lowest / highest: filled dot mid-slot + value label.
      const drawMark = (mark, color, above) => {
        if (!mark || !Number.isInteger(mark.i)) return;
        const mx = x.getPixelForValue(mark.i + 0.5);
        const my = y.getPixelForValue(mark.p);
        c.setLineDash([]);
        c.beginPath();
        c.arc(mx, my, small ? 3.5 : 5, 0, Math.PI * 2);
        c.fillStyle = color;
        c.fill();
        c.lineWidth = 2;
        c.strokeStyle = tok.surface;
        c.stroke();

        const value = fmt(mark.p);
        const timeTxt = small ? "" : ` ${mark.t}`;
        c.font = `800 ${markFont}px ${family}`;
        const wv = c.measureText(value).width;
        c.font = `600 ${Math.round(markFont * 0.85)}px ${family}`;
        const wt = timeTxt ? c.measureText(timeTxt).width : 0;
        const total = wv + wt;
        let lx = mx - total / 2;
        lx = Math.max(area.left + 2, Math.min(area.right - total - 2, lx));
        const ly = above ? my - 9 : my + 9;
        c.textBaseline = above ? "bottom" : "top";
        c.textAlign = "left";
        c.font = `800 ${markFont}px ${family}`;
        c.fillStyle = color;
        c.fillText(value, lx, ly);
        if (timeTxt) {
          c.font = `600 ${Math.round(markFont * 0.85)}px ${family}`;
          c.fillStyle = tok.textMuted;
          c.fillText(timeTxt, lx + wv, ly);
        }
      };
      drawMark(hi, tok.accent1, true);
      drawMark(lo, tok.accent4, false);

      // Now: quiet dashed line + hollow ring, no label (the chip and the
      // legend carry the number). Deliberately below the extremes.
      if (nowX != null) {
        const nx = x.getPixelForValue(nowX);
        const ny = y.getPixelForValue(prices[nowIdx]);
        c.strokeStyle = withAlpha(tok.textPrimary, 0.35);
        c.lineWidth = 1.5;
        c.setLineDash([3, 4]);
        c.beginPath();
        c.moveTo(nx, area.top);
        c.lineTo(nx, area.bottom);
        c.stroke();
        c.setLineDash([]);
        c.beginPath();
        c.arc(nx, ny, small ? 3.5 : 4.5, 0, Math.PI * 2);
        c.fillStyle = tok.surface;
        c.fill();
        c.lineWidth = 2;
        c.strokeStyle = tok.textSecondary;
        c.stroke();
      }
      c.restore();
    },
  };

  const chart = new window.Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: true,
      layout: { padding: { left: 4, right: 4, top: capBand + markBand } },
      scales: {
        x: {
          type: "linear",
          min: 0,
          max: n,
          afterBuildTicks(axis) {
            axis.ticks = tickIdx.map((v) => ({ value: v }));
          },
          ticks: {
            color: tok.textSecondary,
            font: { family: tok.fontFamily, weight: 700, size: tickFontSize },
            maxRotation: 0,
            autoSkip: false,
            callback: (v) => labelAt(Math.round(v)).slice(0, 2),
          },
          grid: { display: false },
          border: { display: false },
        },
        y: {
          display: false,
          // Head-room for the max label (+ day captions) on top and the
          // min label underneath.
          suggestedMin: pMin - span * (small ? 0.3 : cellHeight < 450 ? 0.55 : 0.35),
          suggestedMax: pMax + span * 0.08,
          grid: { display: false },
          border: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
    plugins: [overlay],
  });
  canvas._chart = chart;
}
