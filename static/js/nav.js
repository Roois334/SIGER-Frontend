(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var menus = document.querySelectorAll("[data-menu]");

    function closeAll(except) {
      menus.forEach(function (menu) {
        if (menu === except) return;
        menu.classList.remove("open");
        var trigger = menu.querySelector("[data-menu-trigger]");
        if (trigger) trigger.setAttribute("aria-expanded", "false");
      });
    }

    menus.forEach(function (menu) {
      var trigger = menu.querySelector("[data-menu-trigger]");
      if (!trigger) return;

      trigger.addEventListener("click", function (e) {
        e.stopPropagation();
        var isOpen = menu.classList.contains("open");
        closeAll(menu);
        menu.classList.toggle("open", !isOpen);
        trigger.setAttribute("aria-expanded", String(!isOpen));
      });
    });

    document.addEventListener("click", function () {
      closeAll(null);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAll(null);
    });
  });
})();