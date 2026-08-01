/* 공통 — 네비게이션, 테마, 포맷, 표 렌더 헬퍼. */
(function (g) {
  'use strict';

  var PAGES = [
    ['index.html', '대시보드'],
    ['performance.html', '성과'],
    ['validation.html', '검증'],
    ['research.html', '리서치 로그']
  ];

  function here() {
    var p = location.pathname.split('/').pop();
    return (!p || p === '') ? 'index.html' : p;
  }

  function chrome() {
    var cur = here();
    var bar = document.createElement('header');
    bar.className = 'topbar';
    bar.innerHTML =
      '<div class="topbar-in">' +
      '<a class="brand" href="index.html"><b>추세추종 운용 시스템</b><span>trend-following</span></a>' +
      '<nav>' + PAGES.map(function (p) {
        return '<a href="' + p[0] + '"' + (p[0] === cur ? ' aria-current="page"' : '') + '>' + p[1] + '</a>';
      }).join('') +
      '</nav>' +
      '<span id="refresh-slot"></span>' +
      '<button class="theme-btn" id="theme-btn" title="밝게/어둡게" aria-label="테마 전환">◐</button>' +
      '</div>';
    document.body.insertBefore(bar, document.body.firstChild);
    refresher();

    var btn = document.getElementById('theme-btn');
    btn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var sysDark = matchMedia('(prefers-color-scheme: dark)').matches;
      var next = cur ? (cur === 'dark' ? 'light' : 'dark') : (sysDark ? 'light' : 'dark');
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { }
    });

    var foot = document.createElement('footer');
    var m = (g.QUANT_DATA || {}).meta || {};
    foot.innerHTML =
      '<p><strong>투자 자문이 아닙니다.</strong> 이 사이트는 학습·연구 기록이며, 백테스트 성과는 과거이고 미래를 보장하지 않습니다. ' +
      '실거래 사용을 권장하지 않습니다.</p>' +
      '<p>데이터 ' + (m.period ? m.period[0] + ' ~ ' + m.period[1] : '—') +
      ' · 시세 yfinance(수정주가) · 무위험수익 BIL' +
      ' · 생성 ' + (m.generated_at || '—') +
      ' · <code>python scripts/build_site.py</code> 로 갱신</p>';
    document.body.appendChild(foot);
  }

  /* ------------------------------------------------------------ 갱신 버튼
     scripts/serve.py 로 띄웠을 때만 나타난다. file:// 이나 GitHub Pages 처럼
     백엔드가 없는 곳에서는 /api/status 가 실패하므로 버튼을 숨긴다. */
  function refresher() {
    var slot = document.getElementById('refresh-slot');
    if (!slot || location.protocol === 'file:') return;

    fetch('api/status', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (st) { mount(st); })
      .catch(function () { /* 정적 호스팅 — 버튼 없음 */ });

    function mount(initial) {
      slot.innerHTML =
        '<button class="btn" id="refresh-btn" title="시세를 다시 받아 전체 재계산합니다 (수 분)">↻ 지금 갱신</button>' +
        '<span id="refresh-state" class="refresh-state"></span>';
      var btn = document.getElementById('refresh-btn');
      var state = document.getElementById('refresh-state');
      var polling = null;

      function paint(st) {
        if (st.running) {
          btn.disabled = true;
          btn.textContent = '갱신 중… ' + Math.round(st.pct) + '%';
          state.innerHTML = '<span class="bar"><i style="width:' + st.pct + '%"></i></span>' +
            '<span class="msg">' + st.message + '</span>';
        } else {
          btn.disabled = false;
          btn.textContent = '↻ 지금 갱신';
          if (st.error) {
            state.innerHTML = '<span class="msg err">갱신 실패 — ' + st.error + '</span>';
          } else if (st.finished_at) {
            state.innerHTML = '<span class="msg ok">' + st.message + ' · 새로고침합니다…</span>';
            setTimeout(function () { location.reload(); }, 900);
          } else {
            state.innerHTML = '';
          }
        }
      }

      function poll() {
        fetch('api/status', { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          .then(function (st) {
            paint(st);
            if (!st.running && polling) { clearInterval(polling); polling = null; }
          })
          .catch(function () { });
      }

      btn.addEventListener('click', function () {
        if (btn.disabled) return;
        btn.disabled = true;
        btn.textContent = '시작하는 중…';
        fetch('api/refresh', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (st) {
            paint(st);
            if (!polling) polling = setInterval(poll, 1200);
          })
          .catch(function () {
            btn.disabled = false;
            btn.textContent = '↻ 지금 갱신';
            state.innerHTML = '<span class="msg err">서버에 연결하지 못했습니다</span>';
          });
      });

      /* 다른 탭에서 갱신을 시작해 둔 경우 이어서 표시 */
      if (initial && initial.running) { paint(initial); polling = setInterval(poll, 1200); }
    }
  }

  /* 테마는 페이지 그리기 전에 적용해야 깜빡임이 없다 */
  try {
    var saved = localStorage.getItem('theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) { }

  /* ------------------------------------------------------------ 포맷 */
  var F = {
    pct: function (v, d) { return v == null ? '—' : (v * 100).toFixed(d == null ? 1 : d) + '%'; },
    pctS: function (v, d) {
      if (v == null) return '—';
      var s = (v * 100).toFixed(d == null ? 1 : d) + '%';
      return v > 0 ? '+' + s : s;
    },
    num: function (v, d) { return v == null ? '—' : v.toFixed(d == null ? 2 : d); },
    usd: function (v, d) {
      if (v == null) return '—';
      return (v < 0 ? '−$' : '$') + Math.abs(v).toLocaleString('en-US',
        { minimumFractionDigits: d == null ? 0 : d, maximumFractionDigits: d == null ? 0 : d });
    },
    sh: function (v) { return v == null ? '—' : v.toFixed(3); },
    /* 부호에 따라 색 클래스 — 색만 쓰지 않고 부호(+/−)도 함께 표기한다 */
    sign: function (v) { return v == null ? '' : (v > 0 ? 'pos' : v < 0 ? 'neg' : ''); }
  };

  /* 표 만들기: cols = [{k, label, fmt, cls, num}] */
  function table(rows, cols, opts) {
    opts = opts || {};
    var h = '<div class="tbl-wrap"><table><thead><tr>' +
      cols.map(function (c, i) { return '<th' + (i && c.num !== false ? ' class="num"' : '') + '>' + c.label + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rows.map(function (r) {
        var cls = opts.rowClass ? opts.rowClass(r) : '';
        return '<tr' + (cls ? ' class="' + cls + '"' : '') + '>' +
          cols.map(function (c, i) {
            var v = typeof c.k === 'function' ? c.k(r) : r[c.k];
            var txt = c.fmt ? c.fmt(v, r) : (v == null ? '—' : v);
            var cc = [(i && c.num !== false) ? 'num' : '', c.cls ? c.cls(v, r) : ''].filter(Boolean).join(' ');
            return '<td' + (cc ? ' class="' + cc + '"' : '') + '>' + txt + '</td>';
          }).join('') + '</tr>';
      }).join('') + '</tbody>' +
      (opts.foot ? '<tfoot><tr>' + opts.foot.map(function (c, i) {
        return '<td' + (i ? ' class="num"' : '') + '>' + c + '</td>';
      }).join('') + '</tr></tfoot>' : '') +
      '</table></div>';
    return h;
  }

  /* 범례 (2개 이상 계열이면 항상 표시 — 정체성이 색으로만 전달되면 안 된다) */
  function legend(items, box) {
    return '<div class="legend">' + items.map(function (it) {
      return '<span class="item"><span class="sw' + (box ? ' box' : '') + '" style="background:' + it.color + '"></span>' + it.name + '</span>';
    }).join('') + '</div>';
  }

  /* 차트 헤더 + 표 보기 토글 */
  function chartCard(id, title, hint, opts) {
    opts = opts || {};
    return '<div class="card">' +
      '<div class="chart-head"><h3>' + title + '</h3>' +
      '<div class="chart-tools">' + (opts.tools || '') +
      '<button type="button" data-toggle-table="' + id + '" aria-pressed="false">표로 보기</button></div></div>' +
      (hint ? '<p class="sub" style="margin:-4px 0 10px">' + hint + '</p>' : '') +
      (opts.legend || '') +
      '<div class="chart" id="' + id + '"></div>' +
      '<div class="tbl-view" id="' + id + '-tbl"></div>' +
      '</div>';
  }

  function wireTableToggles() {
    document.querySelectorAll('[data-toggle-table]').forEach(function (b) {
      b.addEventListener('click', function () {
        var t = document.getElementById(b.dataset.toggleTable + '-tbl');
        var on = t.classList.toggle('on');
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        b.textContent = on ? '차트로 보기' : '표로 보기';
      });
    });
  }

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  g.App = { chrome: chrome, F: F, table: table, legend: legend, chartCard: chartCard, wireTableToggles: wireTableToggles, ready: ready, PAGES: PAGES };
})(window);
