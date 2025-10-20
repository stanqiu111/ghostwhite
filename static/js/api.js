function getHeaders() {
  const token = localStorage.getItem("access_token");
  return {

    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}

function getHeadersWithNoContentType() {
  const token = localStorage.getItem("access_token");
  return {
    ...(token && { Authorization: `Bearer ${token}` }),
  };
}