// ==========================
// SHOW / HIDE PASSWORD (login page)
// ==========================

const togglePasswordBtn = document.getElementById("togglePassword");
const passwordField = document.getElementById("password");

if (togglePasswordBtn && passwordField) {
    togglePasswordBtn.addEventListener("click", function () {
        const icon = togglePasswordBtn.querySelector("i");

        if (passwordField.type === "password") {
            passwordField.type = "text";
            icon.classList.remove("bi-eye-fill");
            icon.classList.add("bi-eye-slash-fill");
        } else {
            passwordField.type = "password";
            icon.classList.remove("bi-eye-slash-fill");
            icon.classList.add("bi-eye-fill");
        }
    });
}


// ==========================
// REGISTER PAGE VALIDATION
// ==========================

const usernameInput = document.getElementById("username");
const usernameMessage = document.getElementById("username-message");

const password = document.getElementById("password");
const confirmPassword = document.getElementById("confirm_password");
const passwordMessage = document.getElementById("password-message");

const submitBtn = document.getElementById("submitBtn");

let usernameAvailable = true;
let passwordsMatch = false;

if (usernameInput && usernameMessage) {

    let debounceTimer;

    usernameInput.addEventListener("input", function () {

        clearTimeout(debounceTimer);

        if (usernameInput.value.trim() === "") {
            usernameMessage.innerHTML = "";
            usernameAvailable = false;
            validateForm();
            return;
        }

        debounceTimer = setTimeout(function () {

            fetch("/check_username?username=" + encodeURIComponent(usernameInput.value))
                .then(response => response.json())
                .then(data => {

                    if (data.available) {
                        usernameMessage.innerHTML = "Username available";
                        usernameMessage.style.color = "green";
                        usernameAvailable = true;
                    } else {
                        usernameMessage.innerHTML = "Username already taken";
                        usernameMessage.style.color = "red";
                        usernameAvailable = false;
                    }

                    validateForm();

                });

        }, 350);

    });

}

if (password && confirmPassword && passwordMessage) {
    password.addEventListener("input", validatePasswords);
    confirmPassword.addEventListener("input", validatePasswords);
}

function validatePasswords() {

    if (confirmPassword.value === "") {
        passwordMessage.innerHTML = "";
        passwordsMatch = false;
    } else if (password.value === confirmPassword.value) {
        passwordMessage.innerHTML = "Passwords match";
        passwordMessage.style.color = "green";
        passwordsMatch = true;
    } else {
        passwordMessage.innerHTML = "Passwords do not match";
        passwordMessage.style.color = "red";
        passwordsMatch = false;
    }

    validateForm();

}

function validateForm() {
    if (submitBtn) {
        submitBtn.disabled = !(usernameAvailable && passwordsMatch);
    }
}
