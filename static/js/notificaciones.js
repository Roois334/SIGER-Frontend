(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var raiz = document.getElementById("nf-menu");
    if (!raiz) return;

    var badge = document.getElementById("nf-badge");
    var lista = document.getElementById("nf-list");
    var btnTodas = document.getElementById("nf-todas");
    var URL_RESUMEN = raiz.getAttribute("data-resumen");
    var URL_TODAS = raiz.getAttribute("data-todas");
    var CSRF = raiz.getAttribute("data-csrf");
    var INTERVALO = 30000;
    var ultimo = 0, cargando = false;

    var esc = function (s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    };

    /* Las fechas se guardan en hora de Colombia (UTC-5, sin horario de verano) */
    function hace(iso) {
      var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso || "");
      if (!m) return "";
      var t = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] + 5, +m[5], +(m[6] || 0));
      var min = Math.max(0, Math.round((Date.now() - t) / 60000));
      if (min < 1) return "ahora";
      if (min < 60) return "hace " + min + " min";
      if (min < 1440) return "hace " + Math.floor(min / 60) + " h";
      return "hace " + Math.floor(min / 1440) + " d";
    }

    function pintarContador(n) {
      if (n > 0) { badge.textContent = n > 99 ? "99+" : n; badge.hidden = false; }
      else { badge.hidden = true; }
      raiz.classList.toggle("has-new", n > 0);
      if (btnTodas) btnTodas.disabled = n === 0;
    }

    function pintar(d) {
      pintarContador(d.no_leidas || 0);
      var items = d.notificaciones || [];
      if (!items.length) {
        lista.innerHTML = '<li class="nf-empty">No tienes notificaciones todavía.</li>';
        return;
      }
      lista.innerHTML = items.map(function (n) {
        return '<li><a class="nf-item nf-t-' + esc(n.tipo) + (n.leida ? "" : " is-new") + '" href="' + esc(n.url) + '">' +
          '<span class="nf-dot" aria-hidden="true"></span>' +
          '<span class="nf-item-body"><b>' + esc(n.titulo) + "</b><span>" + esc(n.mensaje) + "</span>" +
          "<small>" + (n.folio ? esc(n.folio) + " · " : "") + esc(hace(n.fecha_creacion)) + "</small></span></a></li>";
      }).join("");
    }

    function cargar() {
      if (cargando) return;
      cargando = true;
      fetch(URL_RESUMEN, { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })
        .then(function (r) {
          var json = (r.headers.get("content-type") || "").indexOf("application/json") !== -1;
          if (!r.ok || !json) throw new Error("no disponible");
          return r.json();
        })
        .then(function (d) { ultimo = Date.now(); pintar(d); })
        .catch(function () {
          if (!lista.querySelector(".nf-item")) lista.innerHTML = '<li class="nf-empty">No se pudieron cargar las notificaciones.</li>';
        })
        .then(function () { cargando = false; });
    }

    if (btnTodas) {
      btnTodas.addEventListener("click", function (e) {
        e.stopPropagation();
        fetch(URL_TODAS, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": CSRF, "X-Requested-With": "fetch" } })
          .then(function () { cargar(); });
      });
    }
    // Al abrir la campana se refresca la lista
    raiz.querySelector("[data-menu-trigger]").addEventListener("click", function () { cargar(); });

    setInterval(function () { if (!document.hidden) cargar(); }, INTERVALO);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && Date.now() - ultimo > INTERVALO) cargar();
    });
    cargar();
  });
})();
