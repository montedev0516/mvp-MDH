// Show loader for form submissions
document.addEventListener("DOMContentLoaded", function () {
  const forms = document.querySelectorAll("form:not(.no-loader)");
  forms.forEach((form) => {
    form.addEventListener("submit", function () {
      showLoader();
    });
  });
});
