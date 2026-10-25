/* Applies the saved theme before the page paints (no flash). Without a saved choice the system theme is used. */
(function () {
  try {
    var theme = localStorage.getItem("advsearch-theme");
    if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
  } catch (e) { /* storage blocked: follow the system theme */ }
})();
