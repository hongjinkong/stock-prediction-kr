/* 자체 SVG 차트 — 외부 라이브러리 없음(오프라인·GitHub Pages 어디서든 동작).
   공통 규칙: 축 하나만 사용 / 2px 선 / 격자는 뒤로 물러남 / 모든 차트에 호버 툴팁 + 표 보기. */
(function (g) {
  'use strict';

  var CSS = function (n) {
    return getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  };
  var SVGNS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, parent) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  var fmt = {
    pct: function (v, d) { return v == null ? '—' : (v * 100).toFixed(d == null ? 1 : d) + '%'; },
    pctS: function (v, d) {
      if (v == null) return '—';
      var s = (v * 100).toFixed(d == null ? 1 : d) + '%';
      return v > 0 ? '+' + s : s;
    },
    num: function (v, d) { return v == null ? '—' : v.toFixed(d == null ? 2 : d); },
    mul: function (v) { return v == null ? '—' : v.toFixed(2) + '배'; },
    usd: function (v) {
      if (v == null) return '—';
      return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
    },
    date: function (s) { return s; }
  };

  /* 눈금 값 — 사람이 읽기 좋은 간격으로 */
  function ticks(lo, hi, n) {
    var span = hi - lo;
    if (!(span > 0)) return [lo];
    var raw = span / (n || 5);
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    var step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
    var out = [], v = Math.ceil(lo / step) * step;
    for (; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }

  /* 툴팁 레이어 */
  function mkTip(host) {
    var t = document.createElement('div');
    t.className = 'tip';
    host.appendChild(t);
    return {
      show: function (x, y, html) { t.innerHTML = html; t.style.left = x + 'px'; t.style.top = (y - 10) + 'px'; t.style.opacity = 1; },
      hide: function () { t.style.opacity = 0; }
    };
  }

  function tipRows(rows) {
    return rows.map(function (r) {
      return '<div class="r"><span class="l">' +
        (r.color ? '<span class="sw" style="background:' + r.color + '"></span>' : '') +
        r.name + '</span><span class="v">' + r.value + '</span></div>';
    }).join('');
  }

  /* 표 보기 토글 — 색만으로 정보를 전달하지 않기 위한 필수 대안 */
  function attachTable(host, cols, rows) {
    var box = document.createElement('div');
    box.className = 'tbl-view';
    var h = '<div class="tbl-wrap"><table><thead><tr>' +
      cols.map(function (c, i) { return '<th' + (i ? ' class="num"' : '') + '>' + c + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr>' + r.map(function (c, i) { return '<td' + (i ? ' class="num"' : '') + '>' + c + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
    box.innerHTML = h;
    host.parentNode.appendChild(box);
    return box;
  }

  /* ------------------------------------------------------------ 선 그래프 */
  function lineChart(host, cfg) {
    host.innerHTML = '';
    host.style.position = 'relative';
    var W = host.clientWidth || 720, H = cfg.height || 300;
    var M = { t: 8, r: 12, b: 24, l: 52 };
    var iw = W - M.l - M.r, ih = H - M.t - M.b;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' }, host);
    if (cfg.title) el('title', {}, svg).textContent = cfg.title;

    var dates = cfg.dates, series = cfg.series, log = !!cfg.log;
    var all = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (v != null && isFinite(v)) all.push(v); }); });
    var lo = cfg.min != null ? cfg.min : Math.min.apply(null, all);
    var hi = cfg.max != null ? cfg.max : Math.max.apply(null, all);
    if (log) { lo = Math.max(lo, 1e-6); }
    var pad = (hi - lo) * 0.06;
    if (!log) { hi += pad; lo -= pad; }
    if (cfg.zeroTop) hi = 0;

    var tf = log ? Math.log10 : function (v) { return v; };
    var Y = function (v) { return M.t + ih - (tf(v) - tf(lo)) / (tf(hi) - tf(lo)) * ih; };
    var X = function (i) { return M.l + (i / (dates.length - 1)) * iw; };

    /* 격자 + y축 */
    var tv = log ? [1, 2, 3, 5, 10, 20, 30].filter(function (v) { return v >= lo && v <= hi; })
      : ticks(lo, hi, cfg.yticks || 5);
    tv.forEach(function (v) {
      var y = Y(v);
      el('line', { x1: M.l, x2: M.l + iw, y1: y, y2: y, stroke: CSS('--grid'), 'stroke-width': 1 }, svg);
      var lb = el('text', { x: M.l - 8, y: y + 3.5, 'text-anchor': 'end', fill: CSS('--muted'), 'font-size': 10.5 }, svg);
      lb.textContent = cfg.yfmt ? cfg.yfmt(v) : v;
    });

    /* x축 — 연 단위 */
    var seen = {};
    dates.forEach(function (d, i) {
      var y = d.slice(0, 4);
      if (seen[y] || (+y) % (cfg.xstep || 2)) { seen[y] = 1; return; }
      seen[y] = 1;
      var x = X(i);
      var lb = el('text', { x: x, y: H - 7, 'text-anchor': 'middle', fill: CSS('--muted'), 'font-size': 10.5 }, svg);
      lb.textContent = y;
    });
    el('line', { x1: M.l, x2: M.l + iw, y1: M.t + ih, y2: M.t + ih, stroke: CSS('--axis'), 'stroke-width': 1 }, svg);

    /* 데이터 */
    series.forEach(function (s) {
      var d = '', open = false;
      s.values.forEach(function (v, i) {
        if (v == null || !isFinite(v)) { open = false; return; }
        d += (open ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1);
        open = true;
      });
      if (s.fill) {
        var fd = d + 'L' + X(s.values.length - 1).toFixed(1) + ' ' + Y(cfg.zeroTop ? 0 : lo).toFixed(1) +
          'L' + X(0).toFixed(1) + ' ' + Y(cfg.zeroTop ? 0 : lo).toFixed(1) + 'Z';
        el('path', { d: fd, fill: s.color, opacity: 0.13 }, svg);
      }
      el('path', {
        d: d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': s.dash || null
      }, svg);
    });

    /* 십자선 + 툴팁 */
    var tip = mkTip(host);
    var cross = el('line', { y1: M.t, y2: M.t + ih, stroke: CSS('--axis'), 'stroke-width': 1, opacity: 0 }, svg);
    var dots = series.map(function (s) {
      return el('circle', { r: 4, fill: s.color, stroke: CSS('--surface'), 'stroke-width': 2, opacity: 0 }, svg);
    });
    var hit = el('rect', { x: M.l, y: M.t, width: iw, height: ih, fill: 'transparent' }, svg);
    hit.style.cursor = 'crosshair';

    function move(ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.round((px - M.l) / iw * (dates.length - 1));
      i = Math.max(0, Math.min(dates.length - 1, i));
      var x = X(i);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('opacity', 1);
      var rows = [];
      series.forEach(function (s, k) {
        var v = s.values[i];
        if (v == null) { dots[k].setAttribute('opacity', 0); return; }
        dots[k].setAttribute('cx', x); dots[k].setAttribute('cy', Y(v)); dots[k].setAttribute('opacity', 1);
        rows.push({ name: s.name, color: s.color, value: (cfg.tfmt || fmt.mul)(v) });
      });
      tip.show(x / W * r.width, Y(series[0].values[i] != null ? series[0].values[i] : lo) / H * r.height,
        '<div class="t">' + dates[i] + '</div>' + tipRows(rows));
    }
    hit.addEventListener('mousemove', move);
    hit.addEventListener('mouseleave', function () {
      tip.hide(); cross.setAttribute('opacity', 0);
      dots.forEach(function (d) { d.setAttribute('opacity', 0); });
    });
    return svg;
  }

  /* ------------------------------------------------------------ 막대(단일/그룹) */
  function barChart(host, cfg) {
    host.innerHTML = '';
    host.style.position = 'relative';
    var W = host.clientWidth || 720, H = cfg.height || 260;
    var M = { t: 8, r: 10, b: cfg.rotate ? 62 : 26, l: 50 };
    var iw = W - M.l - M.r, ih = H - M.t - M.b;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' }, host);

    var cats = cfg.categories, series = cfg.series;
    var all = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (v != null) all.push(v); }); });
    var hi = Math.max.apply(null, all.concat([0]));
    var lo = Math.min.apply(null, all.concat([0]));
    var pad = (hi - lo) * 0.08 || 0.01;
    hi += pad; if (lo < 0) lo -= pad;
    if (cfg.min != null) lo = cfg.min;

    var Y = function (v) { return M.t + ih - (v - lo) / (hi - lo) * ih; };
    /* 막대의 기준선. y축이 0을 포함하지 않을 때(min을 올려 잡은 경우) 0에 붙이면
       막대가 플롯 밖으로 삐져나가므로, 축 범위 안으로 클램프한다. */
    var baseV = Math.min(Math.max(0, lo), hi);
    var gw = iw / cats.length;
    var inner = gw * 0.72, bw = inner / series.length;
    var gap = series.length > 1 ? 2 : 0;   /* 인접 막대 사이 2px 서피스 간격 */

    ticks(lo, hi, 5).forEach(function (v) {
      var y = Y(v);
      el('line', {
        x1: M.l, x2: M.l + iw, y1: y, y2: y,
        stroke: Math.abs(v) < 1e-12 ? CSS('--axis') : CSS('--grid'), 'stroke-width': 1
      }, svg);
      el('text', { x: M.l - 8, y: y + 3.5, 'text-anchor': 'end', fill: CSS('--muted'), 'font-size': 10.5 }, svg)
        .textContent = cfg.yfmt ? cfg.yfmt(v) : v;
    });

    var tip = mkTip(host);
    cats.forEach(function (c, i) {
      var x0 = M.l + i * gw + (gw - inner) / 2;
      series.forEach(function (s, k) {
        var v = s.values[i];
        if (v == null) return;
        var yv = Math.max(M.t, Math.min(M.t + ih, Y(v))), yb = Y(baseV);
        var y0 = Math.min(yv, yb);
        var h = Math.max(Math.abs(yb - yv), 1.5);
        var color = s.colorFn ? s.colorFn(v, i) : s.color;
        var r = el('rect', {
          x: (x0 + k * bw + gap / 2).toFixed(1), y: y0.toFixed(1),
          width: Math.max(bw - gap, 1).toFixed(1), height: h.toFixed(1),
          rx: 3, fill: color, opacity: s.dimFn && s.dimFn(v, i) ? 0.28 : 1
        }, svg);
        r.style.cursor = 'pointer';
        r.addEventListener('mousemove', function (ev) {
          var br = svg.getBoundingClientRect();
          tip.show((ev.clientX - br.left), (ev.clientY - br.top) - 6,
            '<div class="t">' + c + '</div>' +
            tipRows(series.map(function (ss) {
              return { name: ss.name, color: ss.colorFn ? ss.colorFn(ss.values[i], i) : ss.color, value: (cfg.tfmt || fmt.pctS)(ss.values[i]) };
            })));
        });
        r.addEventListener('mouseleave', function () { tip.hide(); });
      });
      var lb = el('text', {
        x: (M.l + i * gw + gw / 2).toFixed(1), y: cfg.rotate ? M.t + ih + 12 : H - 8,
        'text-anchor': cfg.rotate ? 'end' : 'middle', fill: CSS('--muted'), 'font-size': 10.5
      }, svg);
      lb.textContent = c;
      if (cfg.rotate) lb.setAttribute('transform', 'rotate(-38 ' + (M.l + i * gw + gw / 2).toFixed(1) + ' ' + (M.t + ih + 12) + ')');
    });
    return svg;
  }

  /* ------------------------------------------------------------ 가로 막대 (비중) */
  function hbarChart(host, cfg) {
    host.innerHTML = '';
    host.style.position = 'relative';
    var rows = cfg.rows, rh = cfg.rowHeight || 26;
    var W = host.clientWidth || 620, H = rows.length * rh + 8;
    var L = cfg.labelWidth || 108, R = 58;
    var iw = W - L - R;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' }, host);
    var hi = Math.max.apply(null, rows.map(function (r) { return r.value; }).concat([0.01]));
    var tip = mkTip(host);

    rows.forEach(function (r, i) {
      var y = i * rh + 4, bh = rh - 11;
      el('text', { x: 0, y: y + bh / 2 + 4, fill: CSS('--ink-2'), 'font-size': 12, 'font-weight': 500 }, svg)
        .textContent = r.label;
      el('rect', { x: L, y: y, width: iw, height: bh, rx: 3, fill: CSS('--grid'), opacity: 0.5 }, svg);
      var w = Math.max(r.value / hi * iw, r.value > 0 ? 2 : 0);
      var bar = el('rect', {
        x: L, y: y, width: w.toFixed(1), height: bh, rx: 3,
        fill: r.color || CSS('--s1'), opacity: r.dim ? 0.32 : 1
      }, svg);
      bar.style.cursor = 'pointer';
      el('text', {
        x: L + iw + 8, y: y + bh / 2 + 4, fill: CSS('--ink'), 'font-size': 12,
        'font-family': 'ui-monospace, monospace', 'font-weight': 600
      }, svg).textContent = (cfg.vfmt || fmt.pct)(r.value);
      bar.addEventListener('mousemove', function (ev) {
        var br = svg.getBoundingClientRect();
        tip.show(ev.clientX - br.left, ev.clientY - br.top - 6,
          '<div class="t">' + r.label + '</div>' + tipRows(r.detail || [{ name: '비중', color: r.color, value: fmt.pct(r.value) }]));
      });
      bar.addEventListener('mouseleave', function () { tip.hide(); });
    });
    return svg;
  }

  /* ------------------------------------------------------------ 히트맵 (파라미터 민감도) */
  function heatmap(host, cfg) {
    host.innerHTML = '';
    host.style.position = 'relative';
    var xs = cfg.xs, ys = cfg.ys, cells = cfg.cells;   /* cells[y][x] = value */
    var cw = cfg.cellW || 62, ch = cfg.cellH || 34;
    var L = 46, T = 20;
    var W = L + xs.length * cw + 6, H = T + ys.length * ch + 20;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' }, host);
    var ramp = [CSS('--seq-1'), CSS('--seq-2'), CSS('--seq-3'), CSS('--seq-4'), CSS('--seq-5'), CSS('--seq-6')];
    var lo = cfg.min, hi = cfg.max;
    var tip = mkTip(host);

    xs.forEach(function (x, i) {
      el('text', { x: L + i * cw + cw / 2, y: T - 7, 'text-anchor': 'middle', fill: CSS('--muted'), 'font-size': 10.5 }, svg)
        .textContent = x;
    });
    ys.forEach(function (y, j) {
      el('text', { x: L - 8, y: T + j * ch + ch / 2 + 4, 'text-anchor': 'end', fill: CSS('--muted'), 'font-size': 10.5 }, svg)
        .textContent = y;
      xs.forEach(function (x, i) {
        var v = cells[j][i];
        var k = Math.max(0, Math.min(ramp.length - 1, Math.round((v - lo) / (hi - lo) * (ramp.length - 1))));
        var isBase = cfg.baseAt && cfg.baseAt[0] === j && cfg.baseAt[1] === i;
        var r = el('rect', {
          x: L + i * cw + 1, y: T + j * ch + 1, width: cw - 2, height: ch - 2, rx: 4,
          fill: ramp[k], stroke: isBase ? CSS('--ink') : 'none', 'stroke-width': isBase ? 2 : 0
        }, svg);
        r.style.cursor = 'pointer';
        /* 값을 직접 표시 — 색만으로 읽게 하지 않는다 */
        el('text', {
          x: L + i * cw + cw / 2, y: T + j * ch + ch / 2 + 4, 'text-anchor': 'middle',
          fill: k >= 3 ? '#fff' : CSS('--ink'), 'font-size': 11,
          'font-family': 'ui-monospace, monospace', 'font-weight': isBase ? 700 : 500
        }, svg).textContent = v.toFixed(2);
        r.addEventListener('mousemove', function (ev) {
          var br = svg.getBoundingClientRect();
          tip.show(ev.clientX - br.left, ev.clientY - br.top - 6,
            '<div class="t">' + cfg.rowLabel + ' ' + ys[j] + ' · ' + cfg.colLabel + ' ' + xs[i] + '</div>' +
            tipRows((cfg.detail ? cfg.detail(j, i) : [{ name: 'Sharpe', value: v.toFixed(3) }])
              .concat(isBase ? [{ name: '기본 설정', value: '★' }] : [])));
        });
        r.addEventListener('mouseleave', function () { tip.hide(); });
      });
    });
    return svg;
  }

  /* 반응형 — 폭이 바뀌면 다시 그린다 */
  function responsive(host, draw) {
    var t;
    draw();
    var ro = new ResizeObserver(function () {
      clearTimeout(t);
      t = setTimeout(draw, 90);
    });
    ro.observe(host);
    /* 테마 전환 시 CSS 변수로 잡은 색을 다시 읽어야 한다 */
    new MutationObserver(draw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      (mq.addEventListener ? mq.addEventListener.bind(mq, 'change') : mq.addListener.bind(mq))(draw);
    }
  }

  g.Chart = {
    line: lineChart, bar: barChart, hbar: hbarChart, heatmap: heatmap,
    responsive: responsive, table: attachTable, fmt: fmt, css: CSS, ticks: ticks
  };
})(window);
