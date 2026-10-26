/* SIGER - validaciones de formularios (lado del navegador).
   El backend vuelve a validar todo: esto solo da una respuesta inmediata al usuario.

   Atributos que se usan en los formularios:
     <form data-vf>                      activa la revision al enviar
     data-val="nombre|documento|telefono|email"   limpia lo que se escribe y valida el campo
     data-tipo="#id"                     (documento) select con el tipo de documento
     data-opcional                       el campo puede ir vacio
     data-pw-check                       contrasena nueva: muestra los requisitos
     data-pw-confirm="#id"               confirmacion: debe ser igual a la contrasena de #id
     data-eye (boton)                    mostrar / ocultar contrasena
*/
(function () {
  "use strict";

  var LET = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ";
  var OJO = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  var OJO_X = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';

  /* ---------- reglas de contrasena (iguales a las del backend) ---------- */
  var REGLAS = [
    { id: "len", txt: "Mínimo 8 caracteres", ok: function (p) { return p.length >= 8 && p.length <= 128; } },
    { id: "may", txt: "Una letra mayúscula", ok: function (p) { return /[A-ZÁÉÍÓÚÜÑ]/.test(p); } },
    { id: "min", txt: "Una letra minúscula", ok: function (p) { return /[a-záéíóúüñ]/.test(p); } },
    { id: "num", txt: "Un número", ok: function (p) { return /\d/.test(p); } },
    { id: "sim", txt: "Un símbolo (! @ # $ % & * …)", ok: function (p) { return /[^A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ\s]/.test(p); } },
    { id: "esp", txt: "Sin espacios", ok: function (p) { return p.length === 0 || !/\s/.test(p); } }
  ];
  function passwordValida(p) { return REGLAS.every(function (r) { return r.ok(p); }); }

  /* ---------- reglas de campos ---------- */
  var CAMPOS = {
    nombre: {
      limpiar: function (v) { return v.replace(new RegExp("[^" + LET + " '\\-]", "g"), "").replace(/\s{2,}/g, " ").replace(/^[\s'\-]+/, ""); },
      error: function (v) {
        v = v.trim();
        if (!v) return "Este campo es obligatorio";
        if (v.length < 2) return "Escribe al menos 2 letras";
        if (!new RegExp("^[" + LET + "]+(?:[ '\\-][" + LET + "]+)*$").test(v)) return "Usa solo letras";
        return "";
      }
    },
    telefono: {
      limpiar: function (v) { return v.replace(/\D/g, "").slice(0, 10); },
      error: function (v) {
        if (!v) return "Este campo es obligatorio";
        if (/\D/.test(v)) return "Solo números";
        if (!/^(3\d{9}|60\d{8})$/.test(v)) return "Debe tener 10 dígitos y empezar por 3 (ej. 3001234567)";
        return "";
      }
    },
    email: {
      limpiar: function (v) { return v.replace(/\s/g, "").toLowerCase(); },
      error: function (v) {
        if (!v) return "Este campo es obligatorio";
        if (v.length > 120 || !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v)) return "Escribe un correo válido (ej. nombre@correo.com)";
        return "";
      }
    },
    documento: {
      tipo: function (el) { var s = el.getAttribute("data-tipo"); s = s && document.querySelector(s); return s ? s.value : ""; },
      limpiar: function (v, el) {
        if (this.tipo(el) === "PP") return v.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 15);
        return v.replace(/\D/g, "").slice(0, 12);
      },
      error: function (v, el) {
        var t = this.tipo(el);
        if (!v) return "Este campo es obligatorio";
        if (t === "PP") return /^[A-Z0-9]{5,15}$/.test(v) ? "" : "El pasaporte lleva entre 5 y 15 letras o números";
        if (/\D/.test(v)) return "Solo números, sin puntos ni espacios";
        return /^\d{5,12}$/.test(v) ? "" : "Debe tener entre 5 y 12 dígitos";
      }
    }
  };

  /* ---------- mensajes bajo cada campo ---------- */
  function contenedor(input) { return input.closest(".liw, .pf-pw") || input; }
  function mensaje(input) {
    if (input._vfMsg) return input._vfMsg;
    var m = document.createElement("small");
    m.className = "vf-msg"; m.setAttribute("aria-live", "polite");
    contenedor(input).insertAdjacentElement("afterend", m);
    input._vfMsg = m;
    return m;
  }
  function pintar(input, texto, tipo) {
    var m = mensaje(input);
    m.textContent = texto || "";
    m.className = "vf-msg" + (texto ? (tipo === "ok" ? " ok" : " bad") : "");
    input.classList.toggle("is-bad", tipo === "bad" && !!texto);
    input.classList.toggle("is-good", tipo === "ok");
    input.setAttribute("aria-invalid", tipo === "bad" && texto ? "true" : "false");
  }

  function revisarCampo(input, mostrar) {
    var def = CAMPOS[input.getAttribute("data-val")];
    if (!def) return true;
    var v = input.value;
    var vacio = v.trim() === "";
    var err = vacio && input.hasAttribute("data-opcional") ? "" : def.error(v.trim(), input);
    if (mostrar) pintar(input, err, err ? "bad" : (vacio ? "" : "ok"));
    return !err;
  }

  function iniciarCampo(input) {
    var def = CAMPOS[input.getAttribute("data-val")];
    if (!def) return;
    var tocado = false;
    input.addEventListener("input", function () {
      var limpio = def.limpiar(input.value, input);
      if (limpio !== input.value) input.value = limpio;
      if (input.getAttribute("data-val") === "nombre") { /* permite espacios finales mientras se escribe */ }
      revisarCampo(input, tocado || input.value.length > 0);
    });
    input.addEventListener("blur", function () {
      tocado = true;
      if (input.getAttribute("data-val") === "nombre") input.value = input.value.trim();
      revisarCampo(input, true);
    });
    var tipo = input.getAttribute("data-tipo") && document.querySelector(input.getAttribute("data-tipo"));
    if (tipo) tipo.addEventListener("change", function () {
      input.value = def.limpiar(input.value, input);
      if (input.value) revisarCampo(input, true);
    });
  }

  /* ---------- contrasena: lista de requisitos ---------- */
  function iniciarPassword(input) {
    var ul = document.createElement("ul");
    ul.className = "vf-rules"; ul.setAttribute("aria-label", "Requisitos de la contraseña");
    ul.innerHTML = REGLAS.map(function (r) { return '<li data-r="' + r.id + '"><i></i>' + r.txt + "</li>"; }).join("");
    contenedor(input).insertAdjacentElement("afterend", ul);
    function pintarReglas() {
      REGLAS.forEach(function (r) {
        var li = ul.querySelector('[data-r="' + r.id + '"]');
        li.className = input.value ? (r.ok(input.value) ? "is-ok" : "is-bad") : "";
      });
      input.classList.toggle("is-good", !!input.value && passwordValida(input.value));
    }
    input.addEventListener("input", pintarReglas);
    pintarReglas();
  }

  function iniciarConfirmacion(input) {
    var base = document.querySelector(input.getAttribute("data-pw-confirm"));
    if (!base) return;
    function revisar() {
      if (!input.value) { pintar(input, "", ""); return; }
      var igual = input.value === base.value;
      pintar(input, igual ? "Las contraseñas coinciden" : "Las contraseñas no coinciden", igual ? "ok" : "bad");
    }
    input.addEventListener("input", revisar); base.addEventListener("input", revisar);
  }

  /* ---------- ojito ---------- */
  function iniciarOjo(btn) {
    btn.addEventListener("click", function () {
      var i = btn.parentElement.querySelector("input"); if (!i) return;
      var ver = i.type === "password";
      i.type = ver ? "text" : "password";
      btn.classList.toggle("is-on", ver);
      btn.setAttribute("aria-label", ver ? "Ocultar contraseña" : "Mostrar contraseña");
      var svg = btn.querySelector("svg"); if (svg) svg.innerHTML = ver ? OJO_X : OJO;
    });
  }

  /* ---------- envio ---------- */
  function iniciarFormulario(form) {
    form.setAttribute("novalidate", "novalidate");
    form.addEventListener("submit", function (e) {
      var primero = null;
      form.querySelectorAll("[data-val]").forEach(function (inp) {
        if (!revisarCampo(inp, true) && !primero) primero = inp;
      });
      form.querySelectorAll("[data-pw-check]").forEach(function (inp) {
        if (!passwordValida(inp.value)) { inp.classList.add("is-bad"); if (!primero) primero = inp; }
      });
      form.querySelectorAll("[data-pw-confirm]").forEach(function (inp) {
        var base = document.querySelector(inp.getAttribute("data-pw-confirm"));
        if (base && inp.value !== base.value) {
          pintar(inp, "Las contraseñas no coinciden", "bad"); if (!primero) primero = inp;
        }
      });
      form.querySelectorAll("input[required]:not([data-val]):not([data-pw-check]):not([data-pw-confirm]), select[required]").forEach(function (inp) {
        if (!inp.value.trim() && !primero) { inp.classList.add("is-bad"); primero = inp; }
      });
      if (primero) { e.preventDefault(); primero.focus(); }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-val]").forEach(iniciarCampo);
    document.querySelectorAll("[data-pw-check]").forEach(iniciarPassword);
    document.querySelectorAll("[data-pw-confirm]").forEach(iniciarConfirmacion);
    document.querySelectorAll("[data-eye]").forEach(iniciarOjo);
    document.querySelectorAll("form[data-vf]").forEach(iniciarFormulario);
  });
})();
