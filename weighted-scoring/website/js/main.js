/* ==========================================================================
   加权点目围棋 官网 — 共享脚本
   导航高亮 + 移动端菜单切换
   ========================================================================== */
(function () {
    "use strict";

    var path = window.location.pathname.split("/").pop() || "index.html";
    var links = document.querySelectorAll(".nav-links a");
    for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute("href");
        if (href === path || (path === "" && href === "index.html")) {
            links[i].classList.add("active");
        }
    }

    var toggle = document.querySelector(".nav-toggle");
    var menu = document.querySelector(".nav-links");
    if (toggle && menu) {
        toggle.addEventListener("click", function () {
            menu.classList.toggle("open");
        });
        menu.addEventListener("click", function (e) {
            if (e.target.tagName === "A" && window.innerWidth <= 720) {
                menu.classList.remove("open");
            }
        });
    }
})();