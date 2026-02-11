// console.log("Forgot password script loaded");
import { API_BASE_URL } from '../config.js';

// document
//   .getElementById("forgot-password-form")
//   .addEventListener("submit", async (e) => {
//     e.preventDefault();

//     const email = document.getElementById("forgot-email").value.trim();
//     const msg = document.getElementById("fp-msg");

//     msg.style.display = "none";

//     if (!email) {
//       msg.textContent = "Please enter your email.";
//       msg.style.display = "block";
//       return;
//     }

//     try {
//       const res = await fetch("http://localhost:5000/api/forgot-password", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({ email }),
//       });

//       const data = await res.json();

//       if (data.status === "success") {
//         alert("Password reset link sent to your email!");
//         window.location.href = "login.html";
//       } else {
//         msg.textContent = data.message || "Something went wrong";
//         msg.style.display = "block";
//       }
//     } catch (error) {
//       msg.textContent = "Server error. Try again.";
//       msg.style.display = "block";
//     }
//   });

console.log("Forgot password script loaded");

const fpForm = document.getElementById("forgot-password-form");
const fpBtn = document.getElementById("fp-btn");

fpForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("forgot-email").value.trim();
  const msg = document.getElementById("fp-msg");

  msg.style.display = "none";

  if (!email) {
    msg.textContent = "Please enter your email.";
    msg.style.display = "block";
    return;
  }

  // START LOADER
  fpBtn.classList.add("btn-loading");

  try {
    const base = API_BASE_URL.replace(/\/$/, '');
    const res = await fetch(`${base}/api/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    const data = await res.json();

    if (data.status === "success") {
      alert("Password reset link sent to your email!");
      window.location.href = "login.html";
    } else {
      msg.textContent = data.message || "Something went wrong";
      msg.style.display = "block";
    }
  } catch (error) {
    msg.textContent = "Server error. Try again.";
    msg.style.display = "block";
  } finally {
    // STOP LOADER
    fpBtn.classList.remove("btn-loading");
  }
});
