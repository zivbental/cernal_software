/* ============================================================
   CERNAL home page — scroll-driven journey into the cell
   ------------------------------------------------------------
   Chapters (index.html, [data-ch]) are tall sections, each with one
   sticky 100vh stage. This file converts scroll position into a
   0..1 progress per chapter and hands it to a scene:

     enter  -> cell outline zooms until the membrane leaves the screen
     print  -> mRNA strands line up into an expression "fingerprint"
     focus  -> one strand is picked, straightened, its trigger marked
     switch -> lock & key, then the real toehold mechanism (SVG)
     and    -> two locks in series, with live Key A / Key B toggles
     build  -> four pipeline stations open one by one, then the plasmid

   Cheap by construction: the cytoplasm is ~50 polylines on one canvas;
   the SVG scenes move ~100 elements. Nothing is allocated per frame
   except short arrays. Honours prefers-reduced-motion (no ambient
   motion; scrolling still drives the story). Without JavaScript
   index.html stays a readable stack of cards (see cell-home.css).
   ============================================================ */
(function () {
  'use strict';

  var root = document.getElementById('cj');
  if (!root) return;

  var reduceMq = window.matchMedia('(prefers-reduced-motion: reduce)');
  var reduce = reduceMq.matches;
  if (reduceMq.addEventListener) reduceMq.addEventListener('change', function (e) { reduce = e.matches; });

  /* palette = the wiki tokens */
  var C = {
    ink: '#1A1A1A', ink2: '#4A4A4A', joint: '#8F8F8F', chassis: '#DADADA', paper: '#FFFFFF',
    sink: '#F2F2F2', pipe: '#D3E8F5', shade: '#9CC6DF', blue: '#3E5C7E', blueDeep: '#2C4460',
    red: '#C41E3A', redDeep: '#9E1830', redSoft: '#F7DDE2', green: '#2F7D4A', gold: '#A87C12',
    teal: '#1F7A82', tealSoft: '#D8EDEF', violet: '#6A4C93', kraft: '#8C6440'
  };
  var PAL = [C.blue, C.green, C.gold, C.teal, C.violet, C.kraft];
  var MONO = '"Space Mono", ui-monospace, Menlo, monospace';
  var NS = 'http://www.w3.org/2000/svg';

  /* ---------- helpers ---------- */
  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function sm(a, b, x) { var t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); }
  function rng(seed) { // mulberry32: same story for every visitor
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function hex(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
  function mix(c1, c2, t) {
    var a = hex(c1), b = hex(c2);
    return 'rgb(' + Math.round(lerp(a[0], b[0], t)) + ',' + Math.round(lerp(a[1], b[1], t)) + ',' + Math.round(lerp(a[2], b[2], t)) + ')';
  }
  function kf(p, pts) { // piecewise-linear keyframes [[p, v], ...]
    if (p <= pts[0][0]) return pts[0][1];
    for (var i = 1; i < pts.length; i++) {
      if (p <= pts[i][0]) return lerp(pts[i - 1][1], pts[i][1], sm(pts[i - 1][0], pts[i][0], p));
    }
    return pts[pts.length - 1][1];
  }
  var COMP = { A: 'U', U: 'A', G: 'C', C: 'G' };

  /* ---------- scroll bookkeeping ---------- */
  var chs = [].slice.call(root.querySelectorAll('[data-ch]'));
  var byId = {};
  chs.forEach(function (c) { byId[c.id] = c; c._steps = [].slice.call(c.querySelectorAll('.cj-step[data-a]')); });
  var W = 0, H = 0, vh = 0, sy = 0, dirty = true;

  function measure() {
    vh = window.innerHeight;
    sy = window.pageYOffset;
    chs.forEach(function (c) {
      var r = c.getBoundingClientRect();
      c._top = r.top + sy; c._h = c.offsetHeight;
    });
  }
  function prog(c) { return clamp((sy - c._top) / Math.max(1, c._h - vh), 0, 1); }

  /* ======================================================
     SCENE A · the cytoplasm canvas (enter / print / focus)
     ====================================================== */
  var cv = document.getElementById('cjCanvas');
  var cx = cv.getContext('2d');
  var dpr = 1, U = 1, Rw = 1000, s0 = 0.2, narrow = false;
  var N = 51, K = 26;
  var strands = [], dots = [], arcs = [], SEL = 17, seq = '';
  var PS = 1, fx = 0, fy = 0, fxA = 0, fxB = 0, strandsB = [], labelB = null;
  var cells = [];

  function buildCanvas() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    narrow = W < 992;
    U = clamp(Math.min(W, H) / 800, 0.6, 1.25);
    var base = narrow ? Math.min(W * 0.8, H * 0.4) : Math.min(W, H * 0.5);
    Rw = 1.6 * Math.max(W, H);
    s0 = 0.30 * base / Rw;

    // print geometry: concentric ridges, split into one arc per strand
    var counts = [2, 4, 5, 6, 7, 8, 9, 10];
    arcs = [];
    counts.forEach(function (n, k) {
      for (var j = 0; j < n; j++) {
        var span = Math.PI * 2 / n;
        var t0 = k * 0.9 + j * span + 0.08, t1 = k * 0.9 + (j + 1) * span - 0.08;
        arcs.push({ k: k, t0: t0, t1: t1 });
      }
    });
    // one print alone at fx; then A slides to fxA and B emerges to fxB (both stay visible)
    PS = narrow ? Math.min(H * 0.4 / 640, W * 0.4 / 500) : Math.min(H * 0.58 / 640, W * 0.22 / 500);
    fx = narrow ? 0 : W * 0.12;
    fxA = narrow ? -W * 0.25 : W * 0.06;
    fxB = narrow ? W * 0.25 : W * 0.34;
    fy = narrow ? -H * 0.14 : H * 0.02;

    var r = rng(2026);
    strands = [];
    for (var i = 0; i < N; i++) {
      var a = 0.12 + 0.88 * Math.pow(r(), 1.6), b = 0.12 + 0.88 * Math.pow(r(), 1.6);
      strands.push({
        col: PAL[(i * 5 + Math.floor(r() * 3)) % PAL.length],
        A: a, B: b,
        bx: (r() - 0.5) * 1.25 * W, by: (r() - 0.5) * 1.25 * H,
        len: (90 + r() * 120) * U, ang: r() * 6.283,
        amp: (7 + r() * 14) * U, freq: 1 + r() * 1.6, ph: r() * 6.283, sp: 0.35 + r() * 0.6,
        ax: (10 + r() * 24) * U, ay: (10 + r() * 24) * U, dx: 0.15 + r() * 0.35, dy: 0.15 + r() * 0.35, dp: r() * 6.283,
        pt: new Array(K)
      });
      for (var k = 0; k < K; k++) strands[i].pt[k] = [0, 0];
    }
    strands[SEL].A = 1; strands[SEL].B = 0.08; // the transcript that tells the cells apart
    strands.forEach(function (s) { s.diff = s.A - s.B > 0.35; });
    strandsB = strands.map(function (s) {
      var pts = [];
      for (var q = 0; q < K; q++) pts.push([0, 0]);
      return { col: s.col, ab: s.B, diff: s.B - s.A > 0.35, pt: pts };
    });
    dots = [];
    for (i = 0; i < 70; i++) dots.push({ x: (r() - 0.5) * 1.5 * W, y: (r() - 0.5) * 1.5 * H, r: 2 + r() * 4.5, p: r() * 6.28, s: 0.2 + r() * 0.5 });
    cells = [];
    for (i = 0; i < 7; i++) cells.push({ a: i * 6.2832 / 7 + 0.4, d: 2.05 + (i % 2) * 0.08, r: 0.92 + (i % 3) * 0.04 });

    var nts = 'ACGU', RR = rng(7);
    seq = '';
    for (i = 0; i < 80; i++) seq += nts[Math.floor(RR() * 4)];
  }

  var labelEl = document.getElementById('cjPrintLabel');
  if (labelEl && !labelB) {
    labelB = labelEl.cloneNode(false); labelB.id = 'cjPrintLabelB'; labelB.textContent = 'Cell B';
    labelEl.parentNode.insertBefore(labelB, labelEl.nextSibling);
  }
  function placeLabel(l, cxo) {
    var ry = (34 + 7 * 27) * 1.28 * PS * 1.12;
    l.style.left = (W / 2 + cxo) + 'px';
    l.style.top = Math.max(84, H / 2 + fy - ry - 40) + 'px';
  }

  function freePt(s, k, t, out) {
    var u = k / (K - 1), along = (u - 0.5) * s.len;
    var perp = Math.sin(u * s.freq * 6.283 + s.ph + t * s.sp) * s.amp;
    var ca = Math.cos(s.ang), sa = Math.sin(s.ang);
    out[0] = s.bx + Math.sin(t * s.dx + s.dp) * s.ax + along * ca - perp * sa;
    out[1] = s.by + Math.cos(t * s.dy + s.dp) * s.ay + along * sa + perp * ca;
  }
  function printPt(i, k, fB, cxo, out) {
    var a = arcs[i], u = k / (K - 1), kk = a.k, th = lerp(a.t0, a.t1, u) + fB * 0.45 * Math.sin(kk * 1.3 + 1);
    var rr = (34 + kk * 27) * PS;
    var rx = rr * (1 + (0.07 + 0.07 * fB) * Math.sin(3 * th + kk * 0.7 + fB * 3.4));
    var ry = rr * 1.28 * (1 + 0.05 * Math.cos(2 * th + fB * 1.5) + 0.07 * fB);
    out[0] = cxo + kk * 5 * PS * (1 - 2 * fB) * 0.9 + rx * Math.cos(th);
    out[1] = fy + kk * 2 * PS * (0.5 - fB) + ry * Math.sin(th);
  }

  var tmpF = [0, 0], tmpP = [0, 0];
  function strokeStrand(pts, lw, col, alpha) {
    cx.globalAlpha = alpha; cx.strokeStyle = col; cx.fillStyle = col; cx.lineWidth = lw;
    cx.beginPath(); cx.moveTo(pts[0][0], pts[0][1]);
    for (var k = 1; k < K - 1; k++) {
      cx.quadraticCurveTo(pts[k][0], pts[k][1], (pts[k][0] + pts[k + 1][0]) / 2, (pts[k][1] + pts[k + 1][1]) / 2);
    }
    cx.lineTo(pts[K - 1][0], pts[K - 1][1]);
    cx.stroke();
    cx.beginPath(); cx.arc(pts[0][0], pts[0][1], lw * 1.25, 0, 6.283); cx.fill(); // 5' cap
  }

  // glowing stroke: the lines where the two cells differ
  var YEL = '#FFC21A', GLOWRED = '#FF1F45';
  function strokeGlow(pts, lw, base, glowCol, g, alpha) {
    strokeStrand(pts, lw, base, alpha); // the print itself always stays visible
    if (g < 0.02) return;
    cx.shadowColor = glowCol; cx.shadowBlur = 9 * g;
    strokeStrand(pts, lw + 0.8, glowCol, 0.7 * g);
    cx.shadowBlur = 0; cx.shadowColor = 'transparent';
  }

  function drawCell(s, t) {
    var lw = 3.4 / s;
    var j, a, x, y;
    // neighbours (tissue)
    cx.lineWidth = lw; cx.strokeStyle = C.joint;
    cells.forEach(function (c) {
      x = Math.cos(c.a) * c.d * Rw; y = Math.sin(c.a) * c.d * Rw;
      cx.fillStyle = C.sink; cx.beginPath(); cx.arc(x, y, c.r * Rw, 0, 6.283); cx.fill(); cx.stroke();
      cx.fillStyle = C.chassis; cx.beginPath(); cx.arc(x + c.r * Rw * 0.2, y - c.r * Rw * 0.15, c.r * Rw * 0.28, 0, 6.283); cx.fill();
    });
    // the cell (cytoplasm = pipe blue)
    cx.fillStyle = C.pipe; cx.strokeStyle = C.ink; cx.lineWidth = lw;
    cx.beginPath();
    for (j = 0; j <= 120; j++) {
      a = j / 120 * 6.2832;
      var rr = Rw * (1 + 0.012 * Math.sin(5 * a + t * 0.6) + 0.008 * Math.sin(9 * a - t * 0.4));
      if (j) cx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); else cx.moveTo(rr, 0);
    }
    cx.closePath(); cx.fill(); cx.stroke();
    cx.strokeStyle = C.blue; cx.lineWidth = lw * 0.45; cx.setLineDash([lw * 1.4, lw * 1.1]);
    cx.beginPath(); cx.arc(0, 0, Rw * 0.972, 0, 6.283); cx.stroke(); cx.setLineDash([]);
    // nucleus
    cx.fillStyle = C.paper; cx.strokeStyle = C.ink; cx.lineWidth = lw * 0.8; cx.setLineDash([lw * 2, lw]);
    cx.beginPath(); cx.arc(-0.6 * Rw, -0.4 * Rw, 0.22 * Rw, 0, 6.283); cx.fill(); cx.stroke(); cx.setLineDash([]);
  }

  function drawFocusStrand(pc, st, selA) {
    var s = strands[SEL];
    var sp = clamp(W * 0.9 / 44, 15, 26), NT = Math.floor(W * 0.92 / sp);
    var Lt = sm(0.62, 0.82, pc), br = sm(0.78, 0.95, pc);
    var yLine = narrow ? -H * 0.05 : 0;
    var x0 = (-NT / 2 + 0.5) * sp, x1 = (NT / 2 - 0.5) * sp;
    var pts = s._draw, i;
    for (i = 0; i < K; i++) {
      pts[i][0] = lerp(pts[i][0], lerp(x0, x1, i / (K - 1)), st);
      pts[i][1] = lerp(pts[i][1], yLine, st);
    }
    strokeStrand(pts, lerp(4, 7, Lt), selA > 0.3 ? C.ink : s.col, 1);
    if (Lt <= 0.01) return;
    var wl = Math.min(22, NT - 6), ws = Math.floor((NT - wl) / 2);
    cx.globalAlpha = Lt; cx.textAlign = 'center'; cx.textBaseline = 'middle';
    cx.font = '700 ' + Math.round(sp * 0.56) + 'px ' + MONO;
    for (i = 0; i < NT; i++) {
      var bx = x0 + i * sp, inW = i >= ws && i < ws + wl;
      cx.lineWidth = 2.2; cx.strokeStyle = inW ? C.red : C.ink; cx.fillStyle = inW ? C.redSoft : C.paper;
      cx.beginPath(); cx.arc(bx, yLine, sp * 0.45, 0, 6.283); cx.fill(); cx.stroke();
      cx.fillStyle = inW ? C.redDeep : C.ink; cx.fillText(seq[i], bx, yLine + 1);
    }
    cx.font = '700 11px ' + MONO; cx.fillStyle = C.ink2;
    cx.fillText("5′", x0 - sp * 1.1, yLine); cx.fillText("3′", x1 + sp * 1.1, yLine);
    if (br > 0.01) {
      var ax = x0 + ws * sp - sp * 0.5, bx2 = x0 + (ws + wl) * sp - sp * 0.5, by = yLine + sp * 0.95 + (1 - br) * 10;
      cx.globalAlpha = br; cx.strokeStyle = C.red; cx.lineWidth = 3;
      cx.beginPath(); cx.moveTo(ax, by - 7); cx.lineTo(ax, by); cx.lineTo(bx2, by); cx.lineTo(bx2, by - 7); cx.stroke();
      cx.fillStyle = C.red; cx.font = '700 ' + (narrow ? 11 : 13) + 'px ' + MONO;
      cx.fillText('TRIGGER · ' + wl + ' nt · unique to this cell', (ax + bx2) / 2, by + 20);
    }
  }

  function drawCanvas(time) {
    var pe = prog(byId['ch-enter']), pf = prog(byId['ch-print']), pc = prog(byId['ch-focus']);
    var z = sm(0.02, 0.80, pe);
    var s = Math.exp(lerp(Math.log(s0), 0, z));
    var offY = (narrow ? 0.30 : 0.27) * H * (1 - sm(0, 0.4, pe));
    var m = sm(0.0, 0.22, pf) * (1 - sm(0.0, 0.25, pc));
    var fS = sm(0.45, 0.75, pf), cA = lerp(fx, fxA, fS), cB = lerp(fx, fxB, fS);
    var selA = sm(0.18, 0.5, pc), st = sm(0.30, 0.68, pc);

    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx.globalAlpha = 1; cx.fillStyle = C.paper; cx.fillRect(0, 0, W, H);
    cx.save();
    cx.translate(W / 2, H / 2 + offY); cx.scale(s, s);
    cx.lineJoin = 'round'; cx.lineCap = 'round';
    drawCell(s, time);

    var i, k, d, o = (1 - 0.93 * selA);
    // floating small molecules
    cx.fillStyle = C.shade;
    cx.globalAlpha = 0.75 * o * (1 - m * 0.7);
    for (i = 0; i < dots.length; i++) {
      d = dots[i];
      cx.beginPath();
      cx.arc(d.x + Math.sin(time * d.s + d.p) * 18, d.y + Math.cos(time * d.s * 0.8 + d.p) * 18, d.r, 0, 6.283);
      cx.fill();
    }
    var aB = sm(0, 0.3, fS) * (1 - sm(0, 0.2, pc)), fade = 1 - sm(0, 0.2, pc);
    // a soft blink: A and B take turns glowing, then go dark so the print shows through
    var bl = function (ph) { return reduce ? 0.5 : Math.pow(Math.max(0, Math.sin(time * 2.2 + ph)), 2); };
    var gA = sm(0.2, 0.32, pf) * fade * bl(0), gB = sm(0.55, 0.75, pf) * (1 - sm(0, 0.2, pc)) * bl(Math.PI);
    if (aB > 0.01) { // print B, behind A: same ridges, other abundances
      for (i = 0; i < N; i++) {
        var sb = strandsB[i];
        for (k = 0; k < K; k++) printPt(i, k, 1, cB, sb.pt[k]);
        strokeGlow(sb.pt, Math.max(1.6 + 4.2 * sb.ab, 1.1 / s), sb.col, GLOWRED, sb.diff ? gB : 0, (0.28 + 0.72 * sb.ab) * aB);
      }
    }
    for (i = 0; i < N; i++) {
      var sd = strands[i];
      if (!sd._draw) { sd._draw = sd.pt; }
      var mi = sm(0, 1, clamp(m * 1.6 - 0.6 * (i / N), 0, 1));
      for (k = 0; k < K; k++) {
        freePt(sd, k, time, tmpF);
        var pp = sd.pt[k];
        if (mi > 0) {
          printPt(i, k, 0, cA, tmpP);
          pp[0] = lerp(tmpF[0], tmpP[0], mi); pp[1] = lerp(tmpF[1], tmpP[1], mi);
        } else { pp[0] = tmpF[0]; pp[1] = tmpF[1]; }
      }
      if (i === SEL) continue; // drawn last, on top
      var ab = sd.A;
      var lw = Math.max(lerp(2.6, 1.6 + 4.2 * ab, mi), 1.1 / s);
      strokeGlow(sd.pt, lw, sd.col, YEL, sd.diff ? gA * mi * o : 0, lerp(0.85, 0.28 + 0.72 * ab, mi) * o);
    }
    var sel = strands[SEL], abS = sel.A;
    if (pc > 0) {
      drawFocusStrand(pc, st, selA);
    } else {
      var miS = sm(0, 1, clamp(m * 1.6 - 0.6 * (SEL / N), 0, 1));
      strokeGlow(sel.pt, Math.max(lerp(2.6, 1.6 + 4.2 * abS, miS), 1.1 / s),
        sel.col, YEL, gA * miS, lerp(0.85, 0.28 + 0.72 * abS, m));
    }
    cx.restore();
    cx.globalAlpha = 1;

    // hero + cue fade as we dive in; fingerprint label
    var hero = document.getElementById('cjHero'), cue = document.getElementById('cjCue');
    var hv = 1 - sm(0.0, 0.12, pe);
    if (hero) { hero.style.opacity = hv; hero.style.visibility = hv < 0.01 ? 'hidden' : 'visible'; }
    if (cue) { cue.style.opacity = hv; }
    if (labelEl) {
      placeLabel(labelEl, cA); placeLabel(labelB, cB);
      labelEl.style.opacity = m > 0.85 && pc < 0.05 ? 1 : 0;
      labelB.style.opacity = fS > 0.95 && pc < 0.05 ? 1 : 0;
    }
  }

  /* ======================================================
     SCENE B · lock & key, then the real switch (SVG)
     ====================================================== */
  var sw = (function () {
    var svg = document.getElementById('cjSwitch');
    if (!svg) return null;
    var ar = 0.6;
    var TOE = 'AGAGUACA', ARMA = 'GCCUGAUACG', LOOP = 'UGGAGA';
    var ARMB = ARMA.split('').reverse().map(function (c) { return COMP[c]; }).join('');
    var LINK = 'AACAUG';
    var SEQ = TOE + ARMA + LOOP + ARMB + LINK; // 40 nt
    var TRIG = (TOE + ARMA).split('').map(function (c) { return COMP[c]; }).join('');
    var n = SEQ.length, i, k;
    var CL = [], OP = [];
    for (i = 0; i < 8; i++) CL.push([50 + 18 * i, 340]);
    for (i = 0; i < 10; i++) CL.push([194 + 18 * i, 340]);
    for (k = 0; k < 6; k++) { var ph = Math.PI * (k + 1) / 7; CL.push([356 + 36 * Math.sin(ph), 304 + 36 * Math.cos(ph)]); }
    for (i = 0; i < 10; i++) CL.push([356 - 18 * i, 268]);
    [[176, 268], [170, 250], [172, 232], [184, 214], [198, 200], [214, 190]].forEach(function (p) { CL.push(p); });
    for (i = 0; i < 18; i++) OP.push(CL[i]);
    for (k = 0; k < 6; k++) OP.push([374 + 18 * k, 340]);
    for (i = 0; i < 10; i++) OP.push([482 + 18 * i, 340]);
    for (i = 0; i < 6; i++) OP.push([662 + 18 * i, 340]);

    var gBack = el('g', {}, svg), gRung = el('g', {}, svg), gTrig = el('g', {}, svg), gBeads = el('g', {}, svg);
    var gGene = el('g', {}, svg), gLab = el('g', {}, svg), gLock = el('g', {}, svg), gRibo = el('g', {}, svg), gProt = el('g', {}, svg);

    var back = el('path', { fill: 'none', stroke: C.blueDeep, 'stroke-width': 4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, gBack);
    var tailL = el('path', { fill: 'none', stroke: C.joint, 'stroke-width': 4, 'stroke-linecap': 'round' }, gTrig);
    var tailR = el('path', { fill: 'none', stroke: C.joint, 'stroke-width': 4, 'stroke-linecap': 'round' }, gTrig);
    var tback = el('path', { fill: 'none', stroke: C.red, 'stroke-width': 4, 'stroke-linejoin': 'round' }, gTrig);
    var rungs = [], trungs = [], beads = [], letters = [], tbeads = [], tlet = [];
    for (i = 0; i < 10; i++) rungs.push(el('line', { stroke: C.joint, 'stroke-width': 2.5 }, gRung));
    for (i = 0; i < 18; i++) trungs.push(el('line', { stroke: C.red, 'stroke-width': 2, opacity: 0 }, gRung));
    function bead(parent, fill, stroke, ch, fc) {
      var c = el('circle', { r: 8, fill: fill, stroke: stroke, 'stroke-width': 2 }, parent);
      var t = el('text', { 'text-anchor': 'middle', 'font-size': 9, 'font-weight': 700, fill: fc }, parent);
      t.textContent = ch;
      return [c, t];
    }
    for (i = 0; i < 18; i++) { var tb = bead(gTrig, C.redSoft, C.red, TRIG[i], C.redDeep); tbeads.push(tb[0]); tlet.push(tb[1]); }
    for (i = 0; i < n; i++) {
      var f = C.blue, fc = '#fff';
      if (i < 8) { f = C.shade; fc = C.ink; }
      else if (i >= 19 && i <= 22) { f = C.gold; }
      else if (i >= 37) { f = C.green; }
      var b = bead(gBeads, f, C.ink, SEQ[i], fc);
      beads.push(b[0]); letters.push(b[1]);
    }
    var gene = el('rect', { rx: 9, ry: 9, height: 44, width: 360, stroke: C.ink, 'stroke-width': 3 }, gGene);
    var geneT = el('text', { 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700 }, gGene);
    geneT.textContent = 'PAYLOAD GENE';

    function label(txt, col) {
      var t = el('text', { 'font-size': 12, 'font-weight': 700, fill: col || C.ink, 'text-anchor': 'middle', stroke: C.pipe, 'stroke-width': 4, 'paint-order': 'stroke' }, gLab);
      t.textContent = txt; return t;
    }
    var lbToe = label('TOEHOLD'), lbStem = label('STEM'), lbRbs = label('LOOP · RBS', C.gold), lbAug = label('AUG', C.green), lbKey = label('TRIGGER = THE KEY', C.red);

    // padlock glyph that sits on the loop
    var lk = el('g', {}, gLock);
    var shackle = el('path', { d: 'M-9 0 V-9 a9 9 0 0 1 18 0 V0', fill: 'none', stroke: C.ink, 'stroke-width': 4, 'stroke-linecap': 'round' }, lk);
    el('rect', { x: -15, y: 0, width: 30, height: 22, rx: 4, fill: C.blue, stroke: C.ink, 'stroke-width': 3 }, lk);
    el('circle', { cx: 0, cy: 10, r: 3.5, fill: C.pipe }, lk);

    // ribosome
    var rb = el('g', {}, gRibo);
    el('ellipse', { cx: 0, cy: -2, rx: 36, ry: 20, fill: C.chassis, stroke: C.ink, 'stroke-width': 3 }, rb);
    el('ellipse', { cx: -2, cy: -26, rx: 25, ry: 15, fill: C.sink, stroke: C.ink, 'stroke-width': 3 }, rb);
    var rbT = el('text', { y: 4, 'text-anchor': 'middle', 'font-size': 10, 'font-weight': 700, fill: C.ink2 }, rb);
    rbT.textContent = 'RIBOSOME';
    var bonk = el('text', { 'font-size': 22, 'font-weight': 700, fill: C.ink2, 'text-anchor': 'middle' }, gRibo);
    bonk.textContent = '✕';
    var prots = [];
    for (i = 0; i < 10; i++) prots.push(el('circle', { r: 7, fill: C.teal, stroke: C.ink, 'stroke-width': 2 }, gProt));
    var free = [];
    for (i = 0; i < 4; i++) free.push(el('circle', { r: 9, fill: C.teal, stroke: C.ink, 'stroke-width': 2.5 }, gProt));

    var P = [], UB = [];
    for (i = 0; i < n; i++) { P.push([0, 0]); UB.push(0); }

    function setView(p) {
      var wide = W >= 900, Wv = wide ? kf(p, [[0, 760], [0.5, 760], [0.82, 1200]]) : 560;
      var cxw = wide ? kf(p, [[0, 250], [0.45, 250], [0.7, 500], [0.85, 600]]) : kf(p, [[0, 250], [0.3, 250], [0.5, 290], [0.62, 330], [0.78, 480], [0.86, 700], [1, 880]]);
      var Hv = Wv * ar, cyw = 330, fy = wide ? 0.68 : 0.34;
      svg.setAttribute('viewBox', (cxw - Wv / 2) + ' ' + (cyw - Hv * fy) + ' ' + Wv + ' ' + Hv);
    }

    var lkWrap = document.getElementById('cjLockKey'), lkKey = document.getElementById('lkKey'), lkShackle = document.getElementById('lkShackle');

    function update(p, t) {
      ar = (svg.clientHeight || 1) / (svg.clientWidth || 1);
      setView(p);
      // phase 0: lock & key cartoon
      var kp = sm(0.04, 0.15, p), ls = sm(0.15, 0.22, p), fadeOut = sm(0.22, 0.30, p);
      if (lkWrap) {
        lkWrap.style.opacity = 1 - fadeOut; lkWrap.style.transform = 'scale(' + lerp(1, 0.82, fadeOut) + ')';
        lkWrap.style.visibility = fadeOut >= 1 ? 'hidden' : 'visible';
        lkKey.setAttribute('transform', 'translate(' + lerp(60, 210, kp) + ' 176)');
        lkShackle.setAttribute('transform', 'translate(0 ' + (-16 * ls) + ') rotate(' + (-24 * ls) + ' 46 -20)');
      }
      var mol = sm(0.24, 0.33, p);
      svg.style.opacity = mol; svg.style.visibility = mol <= 0 ? 'hidden' : 'visible';
      if (mol <= 0) return;

      var b = sm(0.50, 0.66, p), u = sm(0.60, 0.82, p), tA = sm(0.34, 0.45, p);
      // beads of the switch strand
      for (i = 0; i < n; i++) {
        var ui = i < 18 ? 0 : clamp((u - 0.45 * ((i - 18) / 21)) / 0.55, 0, 1);
        ui = ui * ui * (3 - 2 * ui); UB[i] = ui;
        P[i][0] = lerp(CL[i][0], OP[i][0], ui); P[i][1] = lerp(CL[i][1], OP[i][1], ui);
      }
      var d = 'M' + P[0][0] + ' ' + P[0][1];
      for (i = 1; i < n; i++) d += 'L' + P[i][0].toFixed(1) + ' ' + P[i][1].toFixed(1);
      back.setAttribute('d', d);
      for (i = 0; i < n; i++) {
        beads[i].setAttribute('cx', P[i][0]); beads[i].setAttribute('cy', P[i][1]);
        letters[i].setAttribute('x', P[i][0]); letters[i].setAttribute('y', P[i][1] + 3);
      }
      for (i = 0; i < 10; i++) {
        var A = P[8 + i], B = P[33 - i];
        rungs[i].setAttribute('x1', A[0]); rungs[i].setAttribute('y1', A[1]); rungs[i].setAttribute('x2', B[0]); rungs[i].setAttribute('y2', B[1]);
        rungs[i].setAttribute('opacity', 1 - sm(0, 0.35, UB[33 - i]));
      }
      // trigger (key)
      var e = sm(0, 1, b), wob = (1 - e);
      for (i = 0; i < 18; i++) {
        var tx = 50 + 18 * i - 240 * wob, ty = 360 + 140 * wob + Math.sin(i * 0.5 + t * 3) * 7 * wob;
        tbeads[i].setAttribute('cx', tx); tbeads[i].setAttribute('cy', ty);
        tlet[i].setAttribute('x', tx); tlet[i].setAttribute('y', ty + 3);
        tbeads[i].setAttribute('opacity', tA); tlet[i].setAttribute('opacity', tA);
        var ro = clamp((b - 0.9) * 10 - i * 0.02, 0, 1);
        trungs[i].setAttribute('x1', 50 + 18 * i); trungs[i].setAttribute('y1', 348);
        trungs[i].setAttribute('x2', 50 + 18 * i); trungs[i].setAttribute('y2', 352);
        trungs[i].setAttribute('opacity', ro);
      }
      var t0x = 50 - 240 * wob, t0y = 360 + 140 * wob, t1x = 50 + 17 * 18 - 240 * wob, t1y = 360 + 140 * wob;
      tback.setAttribute('d', 'M' + t0x + ' ' + t0y + 'L' + t1x + ' ' + t1y); tback.setAttribute('opacity', tA);
      tailL.setAttribute('d', 'M' + t0x + ' ' + t0y + 'q-40 20 -90 8 t-90 20'); tailL.setAttribute('opacity', tA);
      tailR.setAttribute('d', 'M' + t1x + ' ' + t1y + 'q40 22 90 6 t80 24'); tailR.setAttribute('opacity', tA);
      // gene
      var gx = P[n - 1][0] + 16, gy = P[n - 1][1], gl = sm(0.84, 0.95, p);
      gene.setAttribute('x', gx); gene.setAttribute('y', gy - 22);
      gene.setAttribute('fill', mix(C.chassis, C.teal, gl));
      geneT.setAttribute('x', gx + 180); geneT.setAttribute('y', gy + 5); geneT.setAttribute('fill', mix(C.ink2, '#FFFFFF', gl));
      // labels
      var lc = P[20], lo = sm(0.56, 0.70, p);
      lbToe.setAttribute('x', P[3][0]); lbToe.setAttribute('y', 322);
      lbStem.setAttribute('x', 275); lbStem.setAttribute('y', 308); lbStem.setAttribute('opacity', 1 - sm(0.6, 0.72, p));
      lbRbs.setAttribute('x', lc[0] + 54); lbRbs.setAttribute('y', lc[1] + (u > 0.5 ? -22 : 4));
      lbAug.setAttribute('x', P[n - 2][0] - 6); lbAug.setAttribute('y', P[n - 2][1] - 22);
      lbKey.setAttribute('x', 50 + 8 * 18 - 240 * wob); lbKey.setAttribute('y', 398 + 140 * wob); lbKey.setAttribute('opacity', tA);
      // lock glyph
      var lkx = lc[0] + 4 + lerp(0, 8, lo);
      lk.setAttribute('transform', 'translate(' + lkx + ' ' + lerp(232, 214, lo) + ')');
      shackle.setAttribute('transform', 'translate(0 ' + (-8 * lo) + ') rotate(' + (-30 * lo) + ' 9 0)');
      lk.setAttribute('opacity', 1 - sm(0.7, 0.78, p));
      // ribosome
      var rbind = sm(0.77, 0.84, p), rs = sm(0.84, 1.0, p);
      var hx = 480 + (reduce ? 0 : 26 * Math.sin(t * 2.4)), hy = 296 + (reduce ? 0 : 6 * Math.sin(t * 5));
      var rx = lerp(hx, lerp(P[20][0] + 2, 1090, rs), rbind), ry = lerp(hy, 314, rbind);
      rb.setAttribute('transform', 'translate(' + rx + ' ' + ry + ')');
      var blocked = rbind < 0.05 && p > 0.3;
      bonk.setAttribute('opacity', blocked && (Math.sin(t * 2.4) > 0.8 || reduce) ? 1 : 0);
      bonk.setAttribute('x', 410); bonk.setAttribute('y', 292);
      // protein chain + released copies
      var np = Math.floor(10 * sm(0.86, 1.0, p));
      for (i = 0; i < 10; i++) {
        prots[i].setAttribute('opacity', i < np ? 1 : 0);
        prots[i].setAttribute('cx', rx + 6 + i * 11); prots[i].setAttribute('cy', ry - 50 - i * 9 + Math.sin(i + t * 3) * (reduce ? 0 : 3));
      }
      var fr = sm(0.92, 0.98, p);
      for (i = 0; i < 4; i++) {
        var ph2 = reduce ? i * 0.25 : ((t * 0.18 + i * 0.25) % 1);
        free[i].setAttribute('cx', 1130 + i * 22 + Math.sin(ph2 * 8 + i) * 8);
        free[i].setAttribute('cy', 300 - ph2 * 150);
        free[i].setAttribute('opacity', fr * (1 - ph2));
      }
    }
    return { update: update };
  })();

  /* ======================================================
     SCENE C · AND gate (two locks, two keys)
     ====================================================== */
  var and = (function () {
    var svg = document.getElementById('cjAnd');
    if (!svg) return null;
    var ar = 0.6, aOn = 0, bOn = 0, aT = 0, bT = 0, manual = null, lastStep = -1;
    var XA = 150, XB = 330, GX = 470, Y = 250;
    var back = el('path', { d: 'M20 ' + Y + 'H' + GX, fill: 'none', stroke: C.joint, 'stroke-width': 5, 'stroke-linecap': 'round' }, svg);
    var gene = el('rect', { x: GX, y: Y - 26, width: 210, height: 52, rx: 10, stroke: C.ink, 'stroke-width': 3 }, svg);
    var geneT = el('text', { x: GX + 105, y: Y + 5, 'text-anchor': 'middle', 'font-size': 14, 'font-weight': 700 }, svg);
    geneT.textContent = 'PAYLOAD GENE';
    function lockG(x, name) {
      var g = el('g', { transform: 'translate(' + x + ' ' + Y + ')' }, svg);
      var sh = el('path', { d: 'M-17 -14 V-30 a17 17 0 0 1 34 0 V-14', fill: 'none', stroke: C.ink, 'stroke-width': 7, 'stroke-linecap': 'round' }, g);
      var body = el('rect', { x: -32, y: -16, width: 64, height: 46, rx: 8, fill: C.blue, stroke: C.ink, 'stroke-width': 4 }, g);
      el('circle', { cx: 0, cy: 6, r: 6, fill: C.pipe }, g);
      var t = el('text', { y: 56, 'text-anchor': 'middle', 'font-size': 14, 'font-weight': 700, fill: C.ink }, g);
      t.textContent = 'LOCK ' + name;
      return { g: g, sh: sh, body: body };
    }
    var LA = lockG(XA, 'A'), LB = lockG(XB, 'B');
    function keyG() {
      var g = el('g', {}, svg);
      el('circle', { cx: 0, cy: 0, r: 17, fill: C.red, stroke: C.ink, 'stroke-width': 3 }, g);
      el('circle', { cx: -3, cy: 0, r: 5, fill: C.pipe }, g);
      el('rect', { x: 15, y: -4, width: 56, height: 8, rx: 2, fill: C.red, stroke: C.ink, 'stroke-width': 3 }, g);
      el('rect', { x: 50, y: 4, width: 7, height: 11, fill: C.red, stroke: C.ink, 'stroke-width': 2.5 }, g);
      el('rect', { x: 62, y: 4, width: 7, height: 8, fill: C.red, stroke: C.ink, 'stroke-width': 2.5 }, g);
      return g;
    }
    var KA = keyG(), KB = keyG();
    var kl1 = el('text', { 'font-size': 13, 'font-weight': 700, fill: C.red, 'text-anchor': 'middle' }, svg); kl1.textContent = 'KEY A';
    var kl2 = el('text', { 'font-size': 13, 'font-weight': 700, fill: C.red, 'text-anchor': 'middle' }, svg); kl2.textContent = 'KEY B';
    var rb = el('g', {}, svg);
    el('ellipse', { cx: 0, cy: -2, rx: 30, ry: 17, fill: C.chassis, stroke: C.ink, 'stroke-width': 3 }, rb);
    el('ellipse', { cx: -2, cy: -22, rx: 21, ry: 13, fill: C.sink, stroke: C.ink, 'stroke-width': 3 }, rb);
    var prots = [];
    for (var i = 0; i < 5; i++) prots.push(el('circle', { r: 8, fill: C.teal, stroke: C.ink, 'stroke-width': 2.5 }, svg));
    var rX = 20, run = 0;

    // standard AND symbol + truth table, lit by the same lock state
    var gg = el('g', { transform: 'translate(250 350)' }, svg);
    var wA0 = el('path', { d: 'M0 22H45', fill: 'none', stroke: C.joint, 'stroke-width': 5, 'stroke-linecap': 'round' }, gg);
    var wB0 = el('path', { d: 'M0 68H45', fill: 'none', stroke: C.joint, 'stroke-width': 5, 'stroke-linecap': 'round' }, gg);
    var wQ0 = el('path', { d: 'M130 45H190', fill: 'none', stroke: C.joint, 'stroke-width': 5, 'stroke-linecap': 'round' }, gg);
    var wA1 = el('path', { d: 'M0 22H45', fill: 'none', stroke: C.red, 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-dasharray': '9 7' }, gg);
    var wB1 = el('path', { d: 'M0 68H45', fill: 'none', stroke: C.red, 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-dasharray': '9 7' }, gg);
    var wQ1 = el('path', { d: 'M130 45H190', fill: 'none', stroke: C.teal, 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-dasharray': '9 7' }, gg);
    var gBody = el('path', { d: 'M45 0H85A45 45 0 0 1 85 90H45Z', stroke: C.ink, 'stroke-width': 4, 'stroke-linejoin': 'round' }, gg);
    var gTxt = el('text', { x: 78, y: 51, 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 700 }, gg); gTxt.textContent = 'AND';
    function gl(x, y, t, a) { var e = el('text', { x: x, y: y, 'text-anchor': a || 'middle', 'font-size': 17, 'font-weight': 700 }, gg); e.textContent = t; return e; }
    var gLA = gl(-14, 28, 'A'), gLB = gl(-14, 74, 'B'), gLQ = gl(206, 51, 'Q', 'start');
    var tt = el('g', { transform: 'translate(480 350)' }, svg);
    var hl = el('rect', { x: -8, y: 20, width: 190, height: 24, rx: 4, stroke: C.ink, 'stroke-width': 2 }, tt);
    [['A', 12], ['B', 72], ['Q', 140]].forEach(function (h) {
      var e = el('text', { x: h[1], y: 12, 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: C.ink2 }, tt); e.textContent = h[0];
    });
    [[0, 0, 0], [0, 1, 0], [1, 0, 0], [1, 1, 1]].forEach(function (r, ri) {
      [12, 72, 140].forEach(function (x, ci) {
        var e = el('text', { x: x, y: 38 + ri * 24, 'text-anchor': 'middle', 'font-size': 14, 'font-weight': 700, fill: C.ink }, tt); e.textContent = r[ci];
      });
    });

    var btnA = document.getElementById('cjKeyA'), btnB = document.getElementById('cjKeyB'), verdict = document.getElementById('cjVerdict');
    function pressed() { return [btnA.getAttribute('aria-pressed') === 'true', btnB.getAttribute('aria-pressed') === 'true']; }
    function setBtn(a, b) { btnA.setAttribute('aria-pressed', a); btnB.setAttribute('aria-pressed', b); }
    btnA.addEventListener('click', function () { var s = pressed(); manual = [!s[0], s[1]]; setBtn(manual[0], manual[1]); });
    btnB.addEventListener('click', function () { var s = pressed(); manual = [s[0], !s[1]]; setBtn(manual[0], manual[1]); });

    var lastT = 0;
    function update(p, t) {
      var dt = Math.min(0.05, t - lastT); if (dt < 0) dt = 0; lastT = t;
      var wide = W >= 900, Wv = wide ? 1050 : 700;
      ar = (svg.clientHeight || 1) / (svg.clientWidth || 1);
      var Hv = Wv * ar;
      svg.setAttribute('viewBox', (wide ? -330 : 0) + ' ' + (230 - Hv * (wide ? 0.5 : 0.34)) + ' ' + Wv + ' ' + Hv);

      var step = p < 0.08 ? 0 : p < 0.33 ? 1 : p < 0.58 ? 2 : 3;
      if (step !== lastStep) { lastStep = step; manual = null; }
      var st = manual || [step === 1 || step === 3, step === 2 || step === 3];
      if (!manual) setBtn(st[0], st[1]);
      aT = st[0] ? 1 : 0; bT = st[1] ? 1 : 0;
      var k = 1 - Math.exp(-dt * 7);
      aOn += (aT - aOn) * k; bOn += (bT - bOn) * k;
      var both = aOn > 0.95 && bOn > 0.95;

      function lockUpd(L, o) {
        L.sh.setAttribute('transform', 'translate(0 ' + (-12 * o) + ') rotate(' + (-34 * o) + ' 17 -14)');
        L.body.setAttribute('fill', mix(C.blue, C.green, o));
      }
      lockUpd(LA, aOn); lockUpd(LB, bOn);
      function keyUpd(g, lbl, x, o) {
        // sits above its lock; drops on when pressed
        var y = lerp(110, 190, o) + (reduce ? 0 : Math.sin(t * 2 + x) * 3 * (1 - o));
        g.setAttribute('transform', 'translate(' + (x - 20) + ' ' + y + ') rotate(' + lerp(0, 0, o) + ')');
        g.setAttribute('opacity', lerp(0.28, 1, o));
        lbl.setAttribute('x', x + 12); lbl.setAttribute('y', y - 28); lbl.setAttribute('opacity', lerp(0.4, 1, o));
      }
      keyUpd(KA, kl1, XA, aOn); keyUpd(KB, kl2, XB, bOn);

      // ribosome walks the chain until it meets a closed lock
      var target = aOn < 0.9 ? XA - 62 : bOn < 0.9 ? XB - 62 : null;
      if (target !== null) {
        rX += (target - rX) * (1 - Math.exp(-dt * 3));
        run = 0;
      } else {
        rX += (reduce ? 0 : 130) * dt; run += dt;
        if (rX > GX + 190) rX = 20;
        if (reduce) rX = GX + 60;
      }
      var bob = reduce ? 0 : Math.sin(t * 6) * 2;
      rb.setAttribute('transform', 'translate(' + rX + ' ' + (Y - 28 + bob) + ')');
      gene.setAttribute('fill', mix(C.chassis, C.teal, both ? 1 : 0));
      geneT.setAttribute('fill', both ? '#FFFFFF' : C.ink2);
      for (var i = 0; i < 5; i++) {
        var ph = reduce ? i * 0.2 : ((t * 0.3 + i * 0.2) % 1);
        prots[i].setAttribute('cx', GX + 40 + i * 36); prots[i].setAttribute('cy', Y - 40 - ph * 90);
        prots[i].setAttribute('opacity', both ? 1 - ph : 0);
      }
      // logic gate: input wires follow the locks, Q follows the payload
      var q = Math.min(aOn, bOn), flow = reduce ? 0 : -t * 40;
      function wire(w0, w1, v) { w1.setAttribute('opacity', v); w1.setAttribute('stroke-dashoffset', flow); w1.setAttribute('stroke-dasharray', reduce ? 'none' : '9 7'); }
      wire(wA0, wA1, aOn); wire(wB0, wB1, bOn); wire(wQ0, wQ1, q);
      gBody.setAttribute('fill', mix(C.paper, C.teal, q)); gTxt.setAttribute('fill', q > 0.5 ? '#FFFFFF' : C.ink);
      gLA.setAttribute('fill', mix(C.ink, C.red, aOn)); gLB.setAttribute('fill', mix(C.ink, C.red, bOn)); gLQ.setAttribute('fill', mix(C.ink, C.teal, q));
      var row = (st[0] ? 2 : 0) + (st[1] ? 1 : 0);
      hl.setAttribute('y', 20 + row * 24); hl.setAttribute('fill', row === 3 ? C.tealSoft : C.redSoft);
      hl.setAttribute('opacity', row === 0 ? 0.5 : 1);
      var txt = 'Key A = ' + (st[0] ? 1 : 0) + ' · Key B = ' + (st[1] ? 1 : 0) + ' → payload ' + (st[0] && st[1] ? 'ON' : 'OFF');
      if (verdict.textContent !== txt) verdict.textContent = txt;
    }
    return { update: update };
  })();

  /* ======================================================
     SCENE D · four stations open, then the plasmid
     ====================================================== */
  var build = (function () {
    var grid = document.getElementById('cjGrid'), ring = document.getElementById('cjRing');
    if (!grid) return null;
    var cards = [].slice.call(grid.querySelectorAll('.cj-stn')), locks = [];
    function padlock(svg, x, y) {
      var g = el('g', { transform: 'translate(' + x + ' ' + y + ')' }, svg);
      var sh = el('path', { d: 'M-7 0 V-7 a7 7 0 0 1 14 0 V0', fill: 'none', stroke: C.ink, 'stroke-width': 3, 'stroke-linecap': 'round' }, g);
      var bd = el('rect', { x: -11, y: 0, width: 22, height: 16, rx: 3, fill: C.blue, stroke: C.ink, 'stroke-width': 2.5 }, g);
      return { sh: sh, bd: bd };
    }
    var i, k;
    // 01 Select: a transcript with one red window
    var s1 = cards[0].querySelector('svg');
    el('path', { d: 'M12 70 q14 -22 28 0 t28 0 t28 0 t28 0 t28 0 t28 0', fill: 'none', stroke: C.ink2, 'stroke-width': 4, 'stroke-linecap': 'round' }, s1);
    el('path', { d: 'M68 70 q14 -22 28 0 t28 0', fill: 'none', stroke: C.red, 'stroke-width': 7, 'stroke-linecap': 'round' }, s1);
    el('path', { d: 'M68 90 v6 h56 v-6', fill: 'none', stroke: C.red, 'stroke-width': 2.5 }, s1);
    // 02 Design: hairpin
    var s2 = cards[1].querySelector('svg');
    el('path', { d: 'M14 78 H120 a16 16 0 0 0 0 -32 H44 a0 0 0 0 0 0 0', fill: 'none', stroke: C.blue, 'stroke-width': 5, 'stroke-linecap': 'round' }, s2);
    el('path', { d: 'M44 46 H60 M44 46 L26 46', stroke: C.blue, 'stroke-width': 5, 'stroke-linecap': 'round' }, s2);
    for (i = 0; i < 6; i++) el('line', { x1: 50 + i * 14, y1: 49, x2: 50 + i * 14, y2: 75, stroke: C.joint, 'stroke-width': 2.5 }, s2);
    el('circle', { cx: 124, cy: 62, r: 6, fill: C.gold, stroke: C.ink, 'stroke-width': 2 }, s2);
    // 03 Rank: bars
    var s3 = cards[2].querySelector('svg');
    for (i = 0; i < 5; i++) {
      el('rect', { x: 14, y: 36 + i * 13, width: 120 - i * 20, height: 9, rx: 2, fill: i === 0 ? C.gold : C.chassis, stroke: C.ink, 'stroke-width': 2 }, s3);
    }
    var t3 = el('text', { x: 144 - 4, y: 44, 'font-size': 12, 'font-weight': 700, fill: C.ink, 'font-family': MONO }, s3); t3.textContent = '#1';
    // 04 Assemble: ring
    var s4 = cards[3].querySelector('svg');
    var segs = [[C.blue, 0], [C.violet, 1], [C.teal, 2], [C.gold, 3]];
    segs.forEach(function (sg) {
      var a0 = sg[1] * 1.5 - 1.2, a1 = a0 + 1.25, R = 32, cxx = 100, cyy = 70;
      el('path', { d: 'M' + (cxx + R * Math.cos(a0)) + ' ' + (cyy + R * Math.sin(a0)) + ' A' + R + ' ' + R + ' 0 0 1 ' + (cxx + R * Math.cos(a1)) + ' ' + (cyy + R * Math.sin(a1)), fill: 'none', stroke: sg[0], 'stroke-width': 9 }, s4);
    });
    cards.forEach(function (c) { locks.push(padlock(c.querySelector('svg'), 178, 14)); });

    // final plasmid ring
    var cxr = 270, cyr = 112, R = 92, arcsR = [
      { n: 'PROMOTER', c: C.blue, a0: -1.6, a1: -0.5 },
      { n: 'TOEHOLD SWITCH', c: C.violet, a0: -0.4, a1: 0.9 },
      { n: 'PAYLOAD', c: C.teal, a0: 1.0, a1: 2.1 },
      { n: 'TERMINATOR', c: C.gold, a0: 2.2, a1: 2.9 }
    ];
    var rarcs = [];
    el('circle', { cx: cxr, cy: cyr, r: R, fill: 'none', stroke: C.chassis, 'stroke-width': 18 }, ring);
    el('circle', { cx: cxr, cy: cyr, r: R, fill: 'none', stroke: C.ink, 'stroke-width': 2, opacity: 0.6 }, ring);
    arcsR.forEach(function (a) {
      var len = (a.a1 - a.a0) * R;
      var path = el('path', {
        d: 'M' + (cxr + R * Math.cos(a.a0)) + ' ' + (cyr + R * Math.sin(a.a0)) + ' A' + R + ' ' + R + ' 0 0 1 ' + (cxr + R * Math.cos(a.a1)) + ' ' + (cyr + R * Math.sin(a.a1)),
        fill: 'none', stroke: a.c, 'stroke-width': 18, 'stroke-dasharray': len, 'stroke-dashoffset': len
      }, ring);
      var mid = (a.a0 + a.a1) / 2, lx = cxr + (R + 34) * Math.cos(mid), ly = cyr + (R + 34) * Math.sin(mid);
      var t = el('text', { x: lx, y: ly + 4, 'text-anchor': Math.cos(mid) > 0.3 ? 'start' : Math.cos(mid) < -0.3 ? 'end' : 'middle', 'font-size': 11, 'font-weight': 700, fill: a.c, 'font-family': MONO, opacity: 0 }, ring);
      t.textContent = a.n;
      rarcs.push({ path: path, len: len, t: t });
    });
    var ct = el('text', { x: cxr, y: cyr - 2, 'text-anchor': 'middle', 'font-size': 20, 'font-weight': 700, fill: C.ink, 'font-family': '"Space Grotesk", sans-serif', opacity: 0 }, ring);
    ct.textContent = 'CERNAL';
    var ct2 = el('text', { x: cxr, y: cyr + 18, 'text-anchor': 'middle', 'font-size': 11, fill: C.ink2, 'font-family': MONO, opacity: 0 }, ring);
    ct2.textContent = 'one plasmid';

    function update(p) {
      for (var j = 0; j < 4; j++) {
        var o = sm(0.04 + 0.15 * j, 0.04 + 0.15 * j + 0.13, p);
        cards[j].style.setProperty('--o', o);
        locks[j].sh.setAttribute('transform', 'translate(0 ' + (-5 * o) + ') rotate(' + (-28 * o) + ' 7 0)');
        locks[j].bd.setAttribute('fill', mix(C.blue, C.green, o));
      }
      for (j = 0; j < rarcs.length; j++) {
        var g = sm(0.66 + 0.06 * j, 0.74 + 0.06 * j, p);
        rarcs[j].path.setAttribute('stroke-dashoffset', rarcs[j].len * (1 - g));
        rarcs[j].t.setAttribute('opacity', g);
      }
      var c = sm(0.9, 1, p); ct.setAttribute('opacity', c); ct2.setAttribute('opacity', c);
    }
    return { update: update };
  })();

  /* ---------- steps, rail, depth ---------- */
  var rail = document.getElementById('cjRail'), depthS = document.getElementById('cjDepthScale'), depthN = document.getElementById('cjDepthName');
  var railLinks = [];
  if (rail) {
    chs.forEach(function (c, idx) {
      var a = document.createElement('a');
      a.href = '#' + c.id; a.setAttribute('aria-label', c.getAttribute('data-title'));
      a.innerHTML = '<span>' + c.getAttribute('data-title') + '</span>';
      a.addEventListener('click', function (e) {
        e.preventDefault();
        measure();
        var frac = idx === 0 ? 0.0 : c.id === 'ch-and' ? 0.3 : c.id === 'ch-build' ? 0.9 : 0.4;
        window.scrollTo({ top: c._top + (c._h - vh) * frac + 1, behavior: reduce ? 'auto' : 'smooth' });
      });
      rail.appendChild(a); railLinks.push(a);
    });
  }

  function updateSteps() {
    var mid = sy + vh * 0.5, active = null;
    chs.forEach(function (c, idx) {
      var p = prog(c);
      c._p = p;
      c._steps.forEach(function (s) {
        var on = sy >= c._top - 1 && p >= parseFloat(s.getAttribute('data-a')) && p < parseFloat(s.getAttribute('data-b'));
        if (on !== s.classList.contains('is-on')) s.classList.toggle('is-on', on);
      });
      if (mid >= c._top && mid < c._top + c._h) active = idx;
    });
    var dp = document.getElementById('cjDepth');
    if (dp) dp.style.visibility = active === null ? 'hidden' : 'visible';
    if (active !== null) {
      railLinks.forEach(function (a, i) { a.classList.toggle('is-on', i === active); });
      var c = chs[active];
      if (depthS && depthS.textContent !== c.getAttribute('data-scale')) {
        depthS.textContent = c.getAttribute('data-scale'); depthN.textContent = c.getAttribute('data-name');
      }
    }
  }

  function inView(c) { return sy + vh > c._top - 50 && sy < c._top + c._h + 50; }

  /* ---------- main loop ---------- */
  var t0 = performance.now(), running = false;
  function frame(now) {
    var t = reduce ? 0 : (now - t0) / 1000;
    var tAny = (now - t0) / 1000; // clock for state easing even when ambient motion is off
    sy = window.pageYOffset;
    updateSteps();
    var focus = byId['ch-focus'];
    if (sy < focus._top + focus._h) drawCanvas(t);
    if (sw && inView(byId['ch-switch'])) sw.update(byId['ch-switch']._p, t);
    if (and && inView(byId['ch-and'])) and.update(byId['ch-and']._p, tAny);
    if (build && inView(byId['ch-build'])) build.update(byId['ch-build']._p);
    requestAnimationFrame(frame);
  }

  function resize() { buildCanvas(); measure(); }
  var rt;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(resize, 120); });
  window.addEventListener('load', measure);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);

  resize();
  requestAnimationFrame(frame);
})();
