function getHeaders() {
  const token = localStorage.getItem("access_token");
  return {

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