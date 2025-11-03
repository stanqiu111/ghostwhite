function getCSRFToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}
function getHeaders() {
  const token = localStorage.getItem("access_token");
  return {
    "X-CSRFToken": getCSRFToken(),
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}

function getHeadersWithNoContentType() {
  // this is used when we need to send with a different content type
  const token = localStorage.getItem("access_token");
  return {
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}