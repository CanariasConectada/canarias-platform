/* Copyright 2026 Canarias Conectada
   License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

/**
 * AJAX like button of the public content cards.
 *
 * Posts to the same server route as the <noscript> form fallback (CSRF
 * token included), then updates the heart icon and the like counter in
 * place instead of reloading the page. The server deduplicates likes per
 * visitor session, so a repeated click is harmless.
 */
(function () {
    "use strict";

    function onLikeClick(button) {
        if (button.dataset.liked === "1" || button.dataset.busy) {
            return;
        }
        button.dataset.busy = "1";
        var body = new FormData();
        body.append("csrf_token", button.dataset.csrf);
        body.append("redirect", window.location.pathname + window.location.search);
        fetch(button.dataset.likeUrl, {
            method: "POST",
            body: body,
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) {
                    return;
                }
                button.dataset.liked = "1";
                button.setAttribute("aria-pressed", "true");
                var icon = button.querySelector(".fa");
                if (icon) {
                    icon.classList.remove("fa-heart-o");
                    icon.classList.add("fa-heart");
                }
                var card = button.closest(".wlc-card");
                var counter = card && card.querySelector(".wlc-like-count");
                if (counter) {
                    counter.textContent = String(
                        (parseInt(counter.textContent, 10) || 0) + 1
                    );
                }
            })
            .finally(function () {
                delete button.dataset.busy;
            });
    }

    document.addEventListener("click", function (event) {
        var button = event.target.closest(".wlc-like-btn[data-like-url]");
        if (button) {
            event.preventDefault();
            onLikeClick(button);
        }
    });
})();
