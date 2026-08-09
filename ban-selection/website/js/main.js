/* ==========================================================================
   20路Ban选围棋 官网 — 共享脚本
   导航高亮 + 移动端菜单切换
   ========================================================================== */
(function () {
    "use strict";

    // 当前页文件名 → 高亮对应导航项
    var path = window.location.pathname.split("/").pop() || "index.html";
    var links = document.querySelectorAll(".nav-links a");
    for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute("href");
        if (href === path || (path === "" && href === "index.html")) {
            links[i].classList.add("active");
        }
    }

    // 移动端汉堡菜单切换
    var toggle = document.querySelector(".nav-toggle");
    var menu = document.querySelector(".nav-links");
    if (toggle && menu) {
        toggle.addEventListener("click", function () {
            menu.classList.toggle("open");
        });
        // 点击菜单项后收起
        menu.addEventListener("click", function (e) {
            if (e.target.tagName === "A" && window.innerWidth <= 720) {
                menu.classList.remove("open");
            }
        });
    }
})();
