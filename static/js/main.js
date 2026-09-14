// Animations légères et confirmations pour actions destructives.

// ===== Mode clair / sombre =====
// Appliqué le plus tôt possible (voir script inline dans <head>) pour éviter
// tout flash de couleur au chargement ; ce bloc gère uniquement le bouton
// de bascule et la persistance du choix.
function basculerTheme() {
  const actuel = document.documentElement.getAttribute("data-theme") || "clair";
  const nouveau = actuel === "sombre" ? "clair" : "sombre";
  document.documentElement.setAttribute("data-theme", nouveau);
  window.localStorage.setItem("dgb_theme", nouveau);
  document.querySelectorAll(".icone-theme").forEach(function (icone) {
    icone.className = "bi icone-theme " + (nouveau === "sombre" ? "bi-sun" : "bi-moon-stars");
  });
}

document.addEventListener("DOMContentLoaded", function () {
  // Icône cohérente avec le thème déjà appliqué (voir script anti-flash du <head>)
  const themeActuel = document.documentElement.getAttribute("data-theme") || "clair";
  document.querySelectorAll(".icone-theme").forEach(function (icone) {
    icone.className = "bi icone-theme " + (themeActuel === "sombre" ? "bi-sun" : "bi-moon-stars");
  });

  document.querySelectorAll("[data-action='basculer-theme']").forEach(function (bouton) {
    bouton.addEventListener("click", basculerTheme);
  });

  // Confirmation générique pour tout bouton/lien marqué data-confirm
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (evt) {
      if (!window.confirm(el.getAttribute("data-confirm"))) {
        evt.preventDefault();
      }
    });
  });

  // Bascule horizon personnalisé (formulaire de prévision)
  const selectHorizon = document.getElementById("id_horizon_predefini");
  const champPerso = document.getElementById("id_horizon_personnalise");
  if (selectHorizon && champPerso) {
    const toggle = function () {
      const actif = selectHorizon.value === "personnalise";
      champPerso.closest(".mb-3, .col-12, div").style.display = actif ? "" : "none";
    };
    selectHorizon.addEventListener("change", toggle);
    toggle();
  }

  // Fermeture auto des messages flash après quelques secondes
  document.querySelectorAll(".alert").forEach(function (alerte, index) {
    setTimeout(function () {
      const closeBtn = alerte.querySelector(".btn-close");
      if (closeBtn) closeBtn.click();
    }, 7000 + index * 300);
  });
});
