document.addEventListener("DOMContentLoaded", () => {
  const toasts = document.querySelectorAll(".toast");
  toasts.forEach((toast, index) => {
    setTimeout(() => {
      toast.classList.add("show");
    }, 150 * index);

    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 250);
    }, 3600 + (index * 200));
  });
});


