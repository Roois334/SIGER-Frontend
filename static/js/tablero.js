(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("es-cfg").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var fmt = function (n) { return Number(n || 0).toLocaleString("es-CO"); };
  var pct = function (n) { return String(n).replace(".", ",") + "%"; };
  var TILDES = { "Inundacion": "Inundación", "Accidente de transito": "Accidente de tránsito", "Emergencia medica": "Emergencia médica" };
  var tipoTxt = function (t) { return TILDES[t] || t; };
  var COL_ESTADO = { pendiente: "var(--am)", asignado: "var(--va)", en_atencion: "#AB47BC", resuelto: "var(--ok)", cerrado: "var(--gs)", descartado: "var(--ra)" };
  var COL_PRIO = { critica: "var(--p-critica)", alta: "var(--p-alta)", media: "var(--p-media)", baja: "var(--p-baja)" };
  var TIP = $("es-tip");
  var periodo = { desde: "", hasta: "" }, peticion = 0, reloj = null, AUTO_MS = 60000;

  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function rango(clave) {
    var h = new Date(), d = new Date();
    if (clave === "todo") return { desde: "", hasta: "" };
    if (clave === "mes") d = new Date(h.getFullYear(), h.getMonth(), 1);
    else if (clave === "anio") d = new Date(h.getFullYear(), 0, 1);
    else d.setDate(h.getDate() - (parseInt(clave, 10) - 1));
    return { desde: iso(d), hasta: iso(h) };
  }
  function qs(f) { return Object.keys(f).filter(function (k) { return f[k]; }).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(f[k]); }).join("&"); }
  function marcarChips() {
    document.querySelectorAll(".es-chip").forEach(function (b) {
      var r = rango(b.getAttribute("data-rango"));
      b.classList.toggle("is-on", r.desde === periodo.desde && r.hasta === periodo.hasta);
    });
  }
  function estado(t, cls) { var e = $("es-estado"); e.textContent = t; e.className = "es-estado " + (cls || ""); }
  function mostrarError(t) { var e = $("es-error"); e.hidden = !t; e.textContent = t || ""; }

  function minutos(m) {
    if (m == null) return "Sin datos";
    m = Math.round(m);
    var d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mi = m % 60;
    if (d) return d + " d " + h + " h";
    if (h) return h + " h " + mi + " min";
    return mi + " min";
  }

  /* ---------------------------------------------------------- indicadores */
  var ICONOS = {
    total: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    activas: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    cerradas: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    criticas: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
  };
  function kpi(clase, icono, titulo, valor, nota) {
    return '<div class="es-kpi ' + clase + '"><span class="es-kpi-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONOS[icono] + '</svg></span>' +
      '<div><small>' + esc(titulo) + '</small><b>' + valor + '</b><em>' + nota + "</em></div></div>";
  }
  function pintarKpis(k) {
    $("es-kpis").innerHTML =
      kpi("", "total", "Total de emergencias", fmt(k.total), fmt(k.afectados) + " personas afectadas") +
      kpi("is-azul", "activas", "Emergencias activas", fmt(k.activas), pct(k.pct_activas) + " del total") +
      kpi("is-verde", "cerradas", "Emergencias cerradas", fmt(k.resueltas), "Resueltas y cerradas · " + pct(k.pct_resueltas)) +
      kpi("is-rojo", "criticas", "Críticas activas", fmt(k.criticas_activas), "Requieren atención inmediata");
  }

  /* ---------------------------------------------------------- barras */
  function barras(id, filas, opts) {
    opts = opts || {};
    var cont = $(id);
    if (!filas.length || !filas.some(function (f) { return f.total; })) { cont.innerHTML = '<p class="es-nada">Sin datos para mostrar.</p>'; return; }
    var max = Math.max.apply(null, filas.map(function (f) { return f.total; })) || 1;
    var activo = opts.filtro ? ($("f-" + opts.filtro) || {}).value : "";
    cont.innerHTML = '<ul class="es-barras">' + filas.map(function (f) {
      var nombre = opts.nombre ? opts.nombre(f.clave) : f.clave;
      var color = opts.color ? opts.color(f.clave) : "var(--grn-solid, var(--va))";
      var valorFiltro = opts.valor ? opts.valor(f) : f.clave;
      var on = activo && activo === String(valorFiltro);
      var tag = opts.filtro ? "button" : "div";
      return '<li><' + tag + (opts.filtro ? ' type="button" class="es-barra' + (on ? " is-on" : "") + '" data-filtro="' + opts.filtro + '" data-valor="' + esc(valorFiltro) + '" title="Filtrar por ' + esc(nombre) + '"' : ' class="es-barra"') + ">" +
        '<span class="es-b-nom">' + esc(nombre) + '</span>' +
        '<span class="es-b-pista"><i style="width:' + Math.max(f.total ? 3 : 0, f.total / max * 100) + '%;background:' + color + '"></i></span>' +
        '<span class="es-b-val"><b>' + fmt(f.total) + '</b><small>' + pct(f.porcentaje) + "</small></span></" + tag + "></li>";
    }).join("") + "</ul>";
  }

  /* ---------------------------------------------------------- donut */
  function donut(id, filas, nombreDe, colorDe, filtro) {
    var cont = $(id), total = filas.reduce(function (a, f) { return a + f.total; }, 0);
    if (!total) { cont.innerHTML = '<p class="es-nada">Sin datos para mostrar.</p>'; return; }
    var R = 54, C = 2 * Math.PI * R, acum = 0, activo = ($("f-" + filtro) || {}).value;
    var arcos = filas.filter(function (f) { return f.total; }).map(function (f) {
      var largo = f.total / total * C, el = '<circle class="es-arco' + (activo === f.clave ? " is-on" : "") + '" data-filtro="' + filtro + '" data-valor="' + esc(f.clave) + '" cx="70" cy="70" r="' + R + '" fill="none" stroke="' + colorDe(f.clave) + '" stroke-width="20" stroke-dasharray="' + Math.max(largo - 1.5, 0.5) + " " + (C - largo + 1.5) + '" stroke-dashoffset="' + (-acum) + '" transform="rotate(-90 70 70)" data-tip="' + esc(nombreDe(f.clave) + ": " + f.total + " (" + pct(f.porcentaje) + ")") + '"></circle>';
      acum += largo; return el;
    }).join("");
    var leyenda = filas.map(function (f) {
      return '<li><button type="button" class="es-leyenda' + (activo === f.clave ? " is-on" : "") + '" data-filtro="' + filtro + '" data-valor="' + esc(f.clave) + '"><i style="background:' + colorDe(f.clave) + '"></i><span>' + esc(nombreDe(f.clave)) + '</span><b>' + fmt(f.total) + '</b><small>' + pct(f.porcentaje) + "</small></button></li>";
    }).join("");
    cont.innerHTML = '<div class="es-donut"><svg viewBox="0 0 140 140" role="img" aria-label="Distribución"><circle cx="70" cy="70" r="' + R + '" fill="none" stroke="var(--borde2)" stroke-width="20"></circle>' + arcos +
      '<text x="70" y="68" text-anchor="middle" class="es-d-num">' + fmt(total) + '</text><text x="70" y="84" text-anchor="middle" class="es-d-txt">emergencias</text></svg><ul>' + leyenda + "</ul></div>";
  }

  /* ---------------------------------------------------------- serie (area) */
  var MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  function etiqueta(e, gran, largo) {
    var p = e.split("-");
    if (gran === "mes") return largo ? MES[+p[1] - 1] + " " + p[0] : MES[+p[1] - 1] + (p[1] === "01" ? " " + p[0].slice(2) : "");
    return (+p[2]) + " " + MES[+p[1] - 1] + (largo ? " " + p[0] : "");
  }
  function serie(s) {
    var cont = $("es-serie"), pts = s.puntos || [];
    $("es-serie-sub").textContent = pts.length ? "Reportes por " + (s.granularidad === "mes" ? "mes" : "día") : "";
    if (!pts.length) { cont.innerHTML = '<p class="es-nada">Sin datos para mostrar.</p>'; return; }
    var W = 1100, H = 270, ml = 38, mr = 14, mt = 14, mb = 30;
    var max = Math.max.apply(null, pts.map(function (p) { return p.total; })), paso = 1;
    max = Math.max(max, 1);
    var pasos = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
    for (var i = 0; i < pasos.length; i++) { paso = pasos[i]; if (max / paso <= 5) break; }
    var tope = Math.ceil(max / paso) * paso;
    var iw = W - ml - mr, ih = H - mt - mb, n = pts.length;
    var X = function (i) { return ml + (n === 1 ? iw / 2 : i / (n - 1) * iw); };
    var Y = function (v) { return mt + ih - v / tope * ih; };
    var grid = "";
    for (var v = 0; v <= tope; v += paso) grid += '<line x1="' + ml + '" x2="' + (W - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="es-grid-l"/><text x="' + (ml - 8) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="es-eje">' + v + "</text>";
    var cada = Math.max(1, Math.ceil(n / 8)), ejeX = "";
    pts.forEach(function (p, i) { if (i % cada === 0 || i === n - 1 && n < 9) ejeX += '<text x="' + X(i) + '" y="' + (H - 8) + '" text-anchor="middle" class="es-eje">' + esc(etiqueta(p.etiqueta, s.granularidad, false)) + "</text>"; });
    var linea = pts.map(function (p, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(p.total).toFixed(1); }).join(" ");
    var area = linea + " L" + X(n - 1).toFixed(1) + " " + (mt + ih) + " L" + X(0).toFixed(1) + " " + (mt + ih) + " Z";
    var zonas = pts.map(function (p, i) {
      var w = n === 1 ? iw : iw / (n - 1);
      return '<rect x="' + (X(i) - w / 2) + '" y="' + mt + '" width="' + w + '" height="' + ih + '" fill="transparent" class="es-zona" data-i="' + i + '" data-tip="' + esc(etiqueta(p.etiqueta, s.granularidad, true) + ": " + p.total + (p.total === 1 ? " emergencia" : " emergencias")) + '"></rect>';
    }).join("");
    var puntos = n <= 45 ? pts.map(function (p, i) { return '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(p.total).toFixed(1) + '" r="3" class="es-punto"/>'; }).join("") : "";
    cont.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" class="es-svg" role="img" aria-label="Emergencias en el tiempo"><defs><linearGradient id="es-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--va)" stop-opacity=".38"/><stop offset="1" stop-color="var(--va)" stop-opacity="0"/></linearGradient></defs>' +
      grid + ejeX + '<path d="' + area + '" fill="url(#es-g)"/><path d="' + linea + '" class="es-linea'+(n>45?" es-fina":"")+'"/>' + puntos + '<line class="es-guia" x1="0" x2="0" y1="' + mt + '" y2="' + (mt + ih) + '" visibility="hidden"/>' + zonas + "</svg>";
    var guia = cont.querySelector(".es-guia");
    cont.querySelectorAll(".es-zona").forEach(function (z) {
      z.addEventListener("mouseenter", function () { var i = +z.getAttribute("data-i"); guia.setAttribute("x1", X(i)); guia.setAttribute("x2", X(i)); guia.setAttribute("visibility", "visible"); });
      z.addEventListener("mouseleave", function () { guia.setAttribute("visibility", "hidden"); });
    });
  }

  /* ---------------------------------------------------------- pintar */
  function pintar(d) {
    pintarKpis(d.kpis);
    var vacio = d.kpis.total === 0;
    $("es-vacio").hidden = !vacio;
    $("es-grid").hidden = vacio;
    if (vacio) return;
    serie(d.serie);
    donut("es-prioridades", d.por_prioridad, function (c) { return CFG.prioridades[c] || c; }, function (c) { return COL_PRIO[c] || "var(--va)"; }, "prioridad");
    donut("es-estados", d.por_estado, function (c) { return CFG.estados[c] || c; }, function (c) { return COL_ESTADO[c] || "var(--va)"; }, "estado");
    var muni = d.por_municipio.filter(function (m) { return m.total > 0; }).sort(function (a, b) { return b.total - a.total; }).slice(0, 8);
    barras("es-municipios", muni, { color: function () { return "linear-gradient(90deg,#1E88E5,#64B5F6)"; } });
    var tipos = d.por_tipo.filter(function (t) { return t.total > 0; }).sort(function (a, b) { return b.total - a.total; });
    barras("es-tipos", tipos, { nombre: tipoTxt, filtro: "tipo", color: function () { return "var(--va)"; } });
  }

  function cargar() {
    marcarChips();
    var q = qs(periodo);
    $("es-exportar").setAttribute("href", CFG.exportar + (q ? "?" + q : ""));
    $("tb-detalle").setAttribute("href", CFG.detalle + (q ? "?" + q : ""));
    mostrarError("");
    var n = ++peticion;
    estado("Actualizando…", "is-wait");
    $("es-grid").classList.add("is-loading");
    fetch(CFG.datos + (q ? "?" + q : ""), { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        var json = (r.headers.get("content-type") || "").indexOf("application/json") !== -1;
        if (r.redirected || r.status === 401 || !json) { window.location = "/login"; throw new Error("sesion"); }
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (x) {
        if (n !== peticion) return;
        if (!x.ok) throw new Error(x.d.error || "No se pudo cargar el dashboard");
        pintar(x.d);
        estado("Actualizado " + new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" }), "is-live");
      })
      .catch(function (e) { if (e.message === "sesion" || n !== peticion) return; mostrarError(e.message); estado("Error al cargar", "is-error"); })
      .then(function () { if (n === peticion) $("es-grid").classList.remove("is-loading"); });
  }

  function programar() {
    clearInterval(reloj); reloj = null;
    if ($("tb-auto").checked) reloj = setInterval(function () { if (!document.hidden) cargar(); }, AUTO_MS);
  }

  document.addEventListener("mousemove", function (e) {
    var t = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!t) { TIP.hidden = true; return; }
    TIP.textContent = t.getAttribute("data-tip"); TIP.hidden = false;
    TIP.style.left = Math.min(e.clientX + 14, window.innerWidth - TIP.offsetWidth - 10) + "px";
    TIP.style.top = (e.clientY + 16) + "px";
  });
  document.querySelectorAll(".es-chip").forEach(function (b) {
    b.addEventListener("click", function () { periodo = rango(b.getAttribute("data-rango")); try { localStorage.setItem("siger-tb-rango", b.getAttribute("data-rango")); } catch (e) {} cargar(); });
  });
  $("tb-refrescar").addEventListener("click", cargar);
  $("tb-auto").addEventListener("change", function () { try { localStorage.setItem("siger-tb-auto", this.checked ? "1" : "0"); } catch (e) {} programar(); });
  // Clic en una porcion o barra: abre Estadisticas con ese filtro y el mismo periodo
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-filtro]") : null;
    if (!b) return;
    var f = { desde: periodo.desde, hasta: periodo.hasta }; f[b.getAttribute("data-filtro")] = b.getAttribute("data-valor");
    window.location = CFG.detalle + "?" + qs(f);
  });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) cargar(); });

  var guardado = "todo";
  try { guardado = localStorage.getItem("siger-tb-rango") || "todo"; $("tb-auto").checked = localStorage.getItem("siger-tb-auto") !== "0"; } catch (e) {}
  periodo = rango(guardado);
  programar();
  cargar();
})();
