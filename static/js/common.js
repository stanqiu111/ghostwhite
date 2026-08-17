// nav bar functions
function logout() {
// Clear every JWT token variant (current + legacy) and identity keys.
// Self-contained so it works on pages that don't load api.js (e.g. streams).
["access_token", "refresh_token", "access", "refresh", "user_id", "username"]
  .forEach((k) => localStorage.removeItem(k));

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
  if (typeof marked === 'undefined') {
    setTimeout(renderMarkdownContent, 100);
    return;
  }
  
  document.querySelectorAll('.entry-content').forEach(node => {
    const type = String(node.dataset.ctype || 'text/plain').toLowerCase();

    // If this entry represents an image (base64 or `image/*`), do NOT echo the raw content.
    // The <img> element below will display it instead.
    if (type.includes('base64') || type.startsWith('image/')) {
      node.textContent = '';
      return;
    }

    if (type.includes('markdown')) {
      const md = (node.textContent || node.innerText || '').trim();
      
      if (md) {
        marked.setOptions({gfm:true,breaks:true});
        node.innerHTML = marked.parse(md);
      }
      return;
    }

    // Otherwise (plain_text etc.) leave as-is.
  });
}

function initMarkdownRendering() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(renderMarkdownContent, 50);
    });
  } else {
    // DOM already loaded, but wait a bit for any dynamic content
    setTimeout(renderMarkdownContent, 50);
  }
}