document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.getElementById("login-error");
  error.textContent = "";
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: document.getElementById("username").value,
      password: document.getElementById("password").value,
    }),
  });
  if (res.ok) {
    window.location.href = "/";
  } else {
    const body = await res.json().catch(() => ({}));
    error.textContent = body.detail || "Sign-in failed";
  }
});
