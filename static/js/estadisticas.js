/* SIGER - graficos de estadisticas (sin librerias externas). Usado por /estadisticas y por el resumen del panel. */
(function () {
  "use strict";

  var NF = new Intl.NumberFormat("es-CO");
  var COLOR_PRIO = { critica: "var(--p-critica)", alta: "var(--p-alta)", media: "var(--p-media)", baja: "var(--p-baja)" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(n) { return NF.format(n || 0); }
  function duracion(min) {
    if (min == null) return "—";
    if (min < 60) return Math.round(min) + " min";
    if (min < 1440) return (min / 60).toFixed(1).replace(".0", "") + " h";
    return (min / 1440).toFixed(1).replace(".0", "") + " d";
  }
  function fechaCorta(iso) {
    var p = String(iso).split("-");   // AAAA-MM-DD -> "22 oct" igual en todos los navegadores
    var meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    return parseInt(p[2], 10) + " " + meses[parseInt(p[1], 10) - 1];
  }
  function maxLimpio(m) {            // 1, 2, 5 x 10^k: ticks con numeros redondos
    if (m <= 4) return 4;
    var p = Math.pow(10, Math.floor(Math.log10(m)));
    var f = m / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }

  /* ------------------------------------------------------------ tarjeta con vista tabla */
  function tarjeta(titulo, subtitulo, graficoHtml, filas, clase) {
    var tabla = '<table class="gx-tabla"><thead><tr><th>Categoría</th><th>Total</th></tr></thead><tbody>' +
      filas.map(function (f) { return "<tr><td>" + esc(f[0]) + "</td><td>" + fmt(f[1]) + "</td></tr>"; }).join("") +
      "</tbody></table>";
    return '<section class="gx-card ' + (clase || "") + '"><header class="gx-card-head"><div><h3>' + esc(titulo) + "</h3>" +
      (subtitulo ? "<p>" + esc(subtitulo) + "</p>" : "") + '</div>' +
      '<button type="button" class="gx-toggle" aria-pressed="false">Ver tabla</button></header>' +
      '<div class="gx-vista-grafico">' + graficoHtml + '</div><div class="gx-vista-tabla" hidden>' + tabla + "</div></section>";
  }

  /* ------------------------------------------------------------ barras horizontales */
  function barras(titulo, subtitulo, items, colorDe, opciones) {
    opciones = opciones || {};
    var total = items.reduce(function (a, i) { return a + i.total; }, 0);
    var max = items.reduce(function (a, i) { return Math.max(a, i.total); }, 0);
    var cuerpo;
    if (!items.length || !total) {
      cuerpo = '<p class="gx-vacio">Sin emergencias para mostrar con estos filtros.</p>';
    } else {
      cuerpo = '<ul class="gx-bars">' + items.map(function (i) {
        var ancho = i.total ? Math.max(2, Math.round(i.total * 100 / max)) : 0;
        var pct = Math.round(i.total * 100 / total);
        return '<li class="gx-row" tabindex="0" data-tip="' + esc(i.nombre + ": " + fmt(i.total) + " (" + pct + "%)") + '">' +
          '<span class="gx-lab">' + esc(i.nombre) + '</span>' +
          '<span class="gx-track"><i style="width:' + ancho + "%;background:" + colorDe(i) + '"></i></span>' +
          '<b class="gx-val">' + fmt(i.total) + "</b></li>";
      }).join("") + "</ul>";
    }
    return tarjeta(titulo, subtitulo, cuerpo, items.map(function (i) { return [i.nombre, i.total]; }), opciones.clase);
  }

  /* ------------------------------------------------------------ columnas en el tiempo */
  function columnas(titulo, subtitulo, serie, semanal) {
    var max = serie.reduce(function (a, p) { return Math.max(a, p.total); }, 0);
    var tope = maxLimpio(max), cuerpo;
    if (!max) {
      cuerpo = '<p class="gx-vacio">Sin emergencias en este periodo.</p>';
    } else {
      var cols = serie.map(function (p) {
        var h = p.total ? Math.max(2, p.total * 100 / tope) : 0;
        var etiqueta = (semanal ? "Semana del " : "") + fechaCorta(p.fecha) + ": " + fmt(p.total) + (p.total === 1 ? " emergencia" : " emergencias");
        return '<div class="gx-col" tabindex="0" data-tip="' + esc(etiqueta) + '"><i style="height:' + h + '%"></i></div>';
      }).join("");
      var n = serie.length, medio = serie[Math.floor(n / 2)];
      cuerpo = '<div class="gx-chart"><div class="gx-y"><span>' + fmt(tope) + "</span><span>" + fmt(tope / 2) + "</span><span>0</span></div>" +
        '<div class="gx-plot"><div class="gx-grid"><i></i><i></i></div><div class="gx-cols">' + cols + "</div></div></div>" +
        '<div class="gx-x"><span>' + esc(fechaCorta(serie[0].fecha)) + "</span>" +
        (n >= 3 ? "<span>" + esc(fechaCorta(medio.fecha)) + "</span>" : "") + (n >= 2 ? "<span>" + esc(fechaCorta(serie[n - 1].fecha)) + "</span>" : "") + "</div>";
    }
    return tarjeta(titulo, subtitulo, cuerpo, serie.map(function (p) { return [(semanal ? "Semana del " : "") + fechaCorta(p.fecha), p.total]; }), "gx-ancha");
  }

  /* ------------------------------------------------------------ indicadores */
  function kpis(d, compacto) {
    var t = d.totales, pct = t.total ? Math.round(t.finalizadas * 100 / t.total) : 0;
    var lista = [
      ["Emergencias activas", fmt(t.activas), "gx-hero", "Pendientes, asignadas o en atención"],
      ["Total registradas", fmt(t.total), "", ""],
      ["Finalizadas", fmt(t.finalizadas), "", pct + "% del total"],
      ["Tiempo hasta asignar", duracion(d.promedio_asignacion_min), "", "Promedio"]
    ];
    if (!compacto) {
      lista.push(["Personas afectadas", fmt(t.afectados), "", ""]);
      lista.push(["Heridos", fmt(t.heridos), "", ""]);
      lista.push(["Descartadas", fmt(t.descartadas), "", "Falsas alarmas o duplicados"]);
    }
    return '<div class="gx-kpis">' + lista.map(function (k) {
      return '<div class="gx-kpi ' + k[2] + '"><span>' + esc(k[0]) + "</span><b>" + esc(k[1]) + "</b>" + (k[3] ? "<small>" + esc(k[3]) + "</small>" : "") + "</div>";
    }).join("") + "</div>";
  }

  var acento = function () { return "var(--va)"; };
  var porPrio = function (i) { return COLOR_PRIO[i.clave] || "var(--va)"; };

  function periodoTexto(d) {
    return d.periodo.personalizado ? "Del " + fechaCorta(d.periodo.desde) + " al " + fechaCorta(d.periodo.hasta)
                                   : "Últimos 30 días";
  }

  function renderCompleto(el, d) {
    var semanal = d.periodo.agrupado === "semana";
    el.innerHTML = kpis(d, false) + '<div class="gx-grid-cards">' +
      barras("Por prioridad", "Cantidad de emergencias", d.por_prioridad, porPrio) +
      barras("Por estado", "Cantidad de emergencias", d.por_estado, acento) +
      barras("Por tipo de emergencia", "De mayor a menor", d.por_tipo, acento) +
      barras("Por municipio", "De mayor a menor", d.por_municipio, acento) +
      columnas("Emergencias en el tiempo", periodoTexto(d) + (semanal ? " · agrupado por semana" : " · por día"), d.por_dia, semanal) +
      "</div>";
  }

  function renderResumen(el, d) {
    el.innerHTML = kpis(d, true) + '<div class="gx-grid-cards">' +
      barras("Distribución por prioridad", "Todas las emergencias registradas", d.por_prioridad, porPrio) +
      barras("Distribución por municipio", "De mayor a menor", d.por_municipio.slice(0, 8), acento) +
      "</div>";
  }

  /* ------------------------------------------------------------ interaccion (tooltip + vista tabla) */
  var tip = null;
  function mostrarTip(el) {
    if (!tip) { tip = document.createElement("div"); tip.className = "gx-tip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
    tip.textContent = el.getAttribute("data-tip");
    tip.style.display = "block";
    var r = el.getBoundingClientRect(), w = tip.offsetWidth;
    tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
    tip.style.top = Math.max(8, r.top - tip.offsetHeight - 8) + "px";
  }
  function ocultarTip() { if (tip) tip.style.display = "none"; }
  document.addEventListener("mouseover", function (e) { var t = e.target.closest && e.target.closest("[data-tip]"); if (t) mostrarTip(t); });
  document.addEventListener("mouseout", function (e) { if (e.target.closest && e.target.closest("[data-tip]")) ocultarTip(); });
  document.addEventListener("focusin", function (e) { var t = e.target.closest && e.target.closest("[data-tip]"); if (t) mostrarTip(t); });
  document.addEventListener("focusout", ocultarTip);
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".gx-toggle");
    if (!b) return;
    var card = b.closest(".gx-card"), tabla = card.querySelector(".gx-vista-tabla"), graf = card.querySelector(".gx-vista-grafico");
    var verTabla = tabla.hidden;
    tabla.hidden = !verTabla; graf.hidden = verTabla;
    b.textContent = verTabla ? "Ver gráfico" : "Ver tabla";
    b.setAttribute("aria-pressed", verTabla ? "true" : "false");
    ocultarTip();
  });

  /* ------------------------------------------------------------ carga */
  function cargar(url, destino, render) {
    destino.innerHTML = '<p class="gx-cargando">Cargando estadísticas…</p>';
    fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) { window.location.reload(); return null; }
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (x) {
        if (!x) return;
        if (!x.ok) { destino.innerHTML = '<p class="gx-error">' + esc(x.d.error || "No se pudieron cargar las estadísticas") + "</p>"; return; }
        render(destino, x.d);
      })
      .catch(function () { destino.innerHTML = '<p class="gx-error">No se pudo conectar con el servidor. Intenta de nuevo.</p>'; });
  }

  window.SigerGX = { cargarCompleto: function (u, el) { cargar(u, el, renderCompleto); }, cargarResumen: function (u, el) { cargar(u, el, renderResumen); } };
})();
