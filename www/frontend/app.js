const form = document.querySelector("#login-form");
const result = document.querySelector("#login-result");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  form.reset();
  result.textContent =
    "Проверка учётной записи будет подключена после переноса таблиц доступа.";
});
