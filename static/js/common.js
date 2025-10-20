// nav bar functions
function logout() {
// Clear JWT tokens from localStorage
localStorage.removeItem("access_token");
localStorage.removeItem("refresh_token");
localStorage.removeItem("user_id");
localStorage.removeItem("username");

window.location.href = "/authors/logout/";
}

function navigateToCreateEntry() {
window.location.href = "/entries/create/";
}

function navigateToProfile(username) {
window.location.href = `/authors/${username}/`;
}

function navigateToHome() {
window.location.href = "/home/";
}