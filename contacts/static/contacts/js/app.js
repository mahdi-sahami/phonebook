document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("global-search");
  const box = document.getElementById("suggestions-box");

  if (!input || !box) return;

  let controller = null;

  const hideSuggestions = () => {
    box.innerHTML = "";
    box.classList.remove("is-visible");
  };

  input.addEventListener("input", async (event) => {
    const value = event.target.value.trim();
    const url = input.dataset.suggestionsUrl;

    if (!value) {
      hideSuggestions();
      return;
    }

    if (controller) controller.abort();
    controller = new AbortController();

    try {
      const response = await fetch(`${url}?q=${encodeURIComponent(value)}`, {
        signal: controller.signal,
        headers: { "X-Requested-With": "XMLHttpRequest" }
      });

      const data = await response.json();
      const suggestions = data.suggestions || [];

      if (!suggestions.length) {
        hideSuggestions();
        return;
      }

      box.innerHTML = suggestions
        .map(item => `<button type="button" class="suggestion-item">${item}</button>`)
        .join("");

      box.classList.add("is-visible");

      box.querySelectorAll(".suggestion-item").forEach(button => {
        button.addEventListener("click", () => {
          input.value = button.textContent.trim();
          document.getElementById("search-form").submit();
        });
      });
    } catch (error) {
      hideSuggestions();
    }
  });

  document.addEventListener("click", (event) => {
    if (!box.contains(event.target) && event.target !== input) {
      hideSuggestions();
    }
  });
});



