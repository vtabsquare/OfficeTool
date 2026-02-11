// console.log("Create new password loaded");
import { API_BASE_URL } from '../config.js';

// document
//   .getElementById("new-password-form")
//   .addEventListener("submit", async (e) => {
//     e.preventDefault();

//     const newPass = document.getElementById("new-pass").value.trim();
//     const confirmPass = document.getElementById("confirm-pass").value.trim();
//     const msg = document.getElementById("np-msg");

//     if (!newPass || !confirmPass) {
//       msg.textContent = "All fields are required.";
//       msg.style.display = "block";
//       return;
//     }

//     if (newPass !== confirmPass) {
//       msg.textContent = "Passwords do not match.";
//       msg.style.display = "block";
//       return;
//     }

//     // CASE 1 → First Login (uses username)
//     const pendingUser = sessionStorage.getItem("pendingUser");

//     // CASE 2 → Forgot Password (uses token)
//     const urlParams = new URLSearchParams(window.location.search);
//     const token = urlParams.get("token");

//     let body = {};

//     if (pendingUser) {
//       console.log("First login mode");
//       body = {
//         username: pendingUser,
//         new_password: newPass,
//       };
//     } else if (token) {
//       console.log("Forgot password mode");
//       body = {
//         token: token,
//         new_password: newPass,
//       };
//     } else {
//       msg.textContent = "Invalid or expired link.";
//       msg.style.display = "block";
//       return;
//     }

//     try {
//       const res = await fetch("http://localhost:5000/api/reset-password", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify(body),
//       });

//       const data = await res.json();

//       if (data.status === "success") {
//         alert("Password updated successfully!");
//         sessionStorage.removeItem("pendingUser");
//         window.location.href = "login.html";
//       } else {
//         msg.textContent = data.message || "Password update failed";
//         msg.style.display = "block";
//       }
//     } catch (err) {
//       msg.textContent = "Network error. Try again.";
//       msg.style.display = "block";
//     }
//   });

console.log("Create new password loaded");

const npForm = document.getElementById("new-password-form");
const npBtn = document.getElementById("np-btn");

npForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const newPass = document.getElementById("new-pass").value.trim();
  const confirmPass = document.getElementById("confirm-pass").value.trim();
  const msg = document.getElementById("np-msg");

  if (!newPass || !confirmPass) {
    msg.textContent = "All fields are required.";
    msg.style.display = "block";
    return;
  }

  if (newPass !== confirmPass) {
    msg.textContent = "Passwords do not match.";
    msg.style.display = "block";
    return;
  }

  const pendingUser = sessionStorage.getItem("pendingUser");
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get("token");

  let body = {};

  if (pendingUser) {
    console.log("First login mode");
    body = {
      username: pendingUser,
      new_password: newPass,
    };
  } else if (token) {
    console.log("Forgot password mode");
    body = {
      token: token,
      new_password: newPass,
    };
  } else {
    msg.textContent = "Invalid or expired link.";
    msg.style.display = "block";
    return;
  }

  // START LOADER
  npBtn.classList.add("btn-loading");

  try {
    const base = API_BASE_URL.replace(/\/$/, '');
    const res = await fetch(`${base}/api/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();

    if (data.status === "success") {
      alert("Password updated successfully!");
      sessionStorage.removeItem("pendingUser");
      window.location.href = "login.html";
    } else {
      msg.textContent = data.message || "Password update failed";
      msg.style.display = "block";
    }
  } catch (err) {
    msg.textContent = "Network error. Try again.";
    msg.style.display = "block";
  } finally {
    // STOP LOADER
    npBtn.classList.remove("btn-loading");
  }
});
