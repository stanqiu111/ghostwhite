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
window.location.href = `/authors/${username}/settings/`;
}

function navigateToPublicProfile(username) {
window.location.href = `/authors/${username}/`;
}

function navigateToHome() {
window.location.href = "/home/";
}

function renderSafeMarkdown(mdText) {
  // Check if libraries are available
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    console.error('marked or DOMPurify not loaded');
    return mdText || ''; // Return raw text if libraries aren't available
  }
  
  // convert markdown -> html and sanitize
  marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false });
  const rawHtml = marked.parse(mdText || '');

  const cleanHtml = DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      'p','br','strong','em','s','code','pre','blockquote',
      'ul','ol','li','h1','h2','h3','h4','h5','h6','hr',
      'a','img'
    ],
    ALLOWED_ATTR: [
      'href','title','target','rel',                // for <a>
      'src','alt','width','height','loading','decoding','referrerpolicy' // for <img>
    ],
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['style','svg','math','form','input','button','iframe','script']
  });
  // ensure safe links
  const tmp = document.createElement('div');
  tmp.innerHTML = cleanHtml;
  tmp.querySelectorAll('a[target="_blank"]').forEach(a => {
    if (!/noopener|noreferrer/.test(a.rel)) a.rel = 'noopener noreferrer';
  });
  return tmp.innerHTML;
}

// Apply markdown rendering to all .entry-content elements on the page
function renderMarkdownContent() {
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    // Libraries not loaded yet, try again after a short delay
    setTimeout(renderMarkdownContent, 100);
    return;
  }
  
  document.querySelectorAll('.entry-content').forEach(node => {
    const type = String(node.dataset.ctype || 'plain_text').toLowerCase();

    // If this entry represents an image (base64 or `image/*`), do NOT echo the raw content.
    // The <img> element below will display it instead.
    if (type.includes('base64') || type.startsWith('image/')) {
      node.textContent = '';
      return;
    }

    // Markdown -> safe HTML
    if (type.includes('markdown')) {
      const md = node.textContent; // raw markdown text
      node.innerHTML = renderSafeMarkdown(md);
      return;
    }

    // Otherwise (plain_text etc.) leave as-is.
  });
}

function initMarkdownRendering() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderMarkdownContent);
  } else {
    renderMarkdownContent();
  }
}