(function () {
  "use strict";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll(".theme-btn").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.theme === theme);
    });
  }

  function setTheme(theme) {
    localStorage.setItem("siger-theme", theme);
    applyTheme(theme);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var saved = localStorage.getItem("siger-theme") || "dark";
    applyTheme(saved);

    document.querySelectorAll(".theme-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setTheme(btn.dataset.theme);
      });
    });
  });
})();
