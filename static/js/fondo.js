/* Fondo animado: particulas luminosas que caen suavemente sobre el logo difuminado.
   Se pausa si la pestana esta oculta y se apaga si el usuario pidio menos movimiento. */
(function () {
  "use strict";
  var cv = document.getElementById("bg-particulas");
  if (!cv || !cv.getContext) return;
  var reducir = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ctx = cv.getContext("2d");
  var W = 0, H = 0, dpr = 1, ps = [], raf = 0, ultimo = 0;

  function claro() { return document.documentElement.getAttribute("data-theme") === "light"; }
  function cantidad() { return Math.max(24, Math.min(70, Math.round(W * H / 26000))); }

  function nueva(arriba) {
    var r = Math.random();
    return {
      x: Math.random() * W,
      y: arriba ? -10 - Math.random() * 40 : Math.random() * H,
      r: 0.8 + r * r * 2.6,                 // la mayoria pequenas, pocas grandes
      v: 14 + Math.random() * 30 + r * 16,  // velocidad de caida (px/s)
      a: 0.25 + Math.random() * 0.55,       // brillo
      s: Math.random() * Math.PI * 2,       // fase del vaiven
      w: 6 + Math.random() * 16,            // amplitud del vaiven
      c: Math.random() < 0.72 ? 0 : 1       // 0 azul, 1 cian
    };
  }

  function medir() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    cv.style.width = W + "px"; cv.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var n = cantidad();
    while (ps.length < n) ps.push(nueva(false));
    ps.length = n;
  }

  function pintar(t) {
    ctx.clearRect(0, 0, W, H);
    var lc = claro();
    for (var i = 0; i < ps.length; i++) {
      var p = ps[i];
      var x = p.x + Math.sin(t / 1800 + p.s) * p.w;
      var base = lc ? "21,101,192" : (p.c ? "100,220,255" : "100,181,246");
      var al = p.a * (lc ? 0.85 : 1);
      var g = ctx.createRadialGradient(x, p.y, 0, x, p.y, p.r * 4.2);
      g.addColorStop(0, "rgba(" + base + "," + al + ")");
      g.addColorStop(0.35, "rgba(" + base + "," + (al * 0.35) + ")");
      g.addColorStop(1, "rgba(" + base + ",0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, p.y, p.r * 4.2, 0, 6.2832); ctx.fill();
    }
  }

  function paso(ahora) {
    var dt = Math.min((ahora - (ultimo || ahora)) / 1000, 0.05);
    ultimo = ahora;
    for (var i = 0; i < ps.length; i++) {
      var p = ps[i];
      p.y += p.v * dt;
      if (p.y > H + 12) ps[i] = nueva(true);
    }
    pintar(ahora);
    raf = requestAnimationFrame(paso);
  }

  function iniciar() { if (!raf && !reducir) { ultimo = 0; raf = requestAnimationFrame(paso); } }
  function parar() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

  medir();
  if (reducir) { pintar(0); } else { iniciar(); }
  var tr;
  window.addEventListener("resize", function () { clearTimeout(tr); tr = setTimeout(function () { medir(); if (reducir) pintar(0); }, 150); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) parar(); else iniciar(); });
})();
