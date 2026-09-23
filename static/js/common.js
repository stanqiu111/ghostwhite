// nav bar functions
function logout() {
// Clear every JWT token variant (current + legacy) and identity keys.
// Self-contained so it works on pages that don't load api.js (e.g. streams).
["access_token", "refresh_token", "access", "refresh", "user_id", "username"]
  .forEach((k) => localStorage.removeItem(k));

window.location.href = "/authors/logout/";
}

/*
 * Unread dot on the header's Inbox bell. The bell now lives in the shared
 * header partial, so its visibility is driven from here rather than each
 * page owning a differently-named copy.
 */
function setNavNotifDot(count) {
  const dot = document.getElementById("navNotifDot");
  if (dot) dot.setAttribute("display", count > 0 ? "inline" : "none");
}

/* ──────────────────────────────────────────────────────────────
 * Theme (light / dark)
 *
 * One implementation for every page: state lives in localStorage under
 * "theme" and is expressed as data-theme on <html>, which theme.css keys off.
 * Pages only need to load common.js + theme.css and, optionally, include a
 * button with id="themeToggle" containing an <svg id="themeIcon">.
 * ────────────────────────────────────────────────────────────── */
const THEME_SUN_SVG = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
const THEME_MOON_SVG = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';

function prefersDarkTheme() {
  try {
    const stored = localStorage.getItem("theme");
    if (stored === "dark") return true;
    if (stored === "light") return false;
  } catch (e) { /* private mode / blocked storage */ }
  // No explicit choice yet: follow the OS.
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function updateThemeIcon(dark) {
  const icon = document.getElementById("themeIcon");
  if (icon) icon.innerHTML = dark ? THEME_SUN_SVG : THEME_MOON_SVG;
  const btn = document.getElementById("themeToggle");
  if (btn) btn.setAttribute("title", dark ? "Switch to light mode" : "Switch to dark mode");
}

function applyTheme(dark) {
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  updateThemeIcon(dark);
}

function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") !== "dark";
  try { localStorage.setItem("theme", next ? "dark" : "light"); } catch (e) {}
  applyTheme(next);
}

// Runs as soon as common.js is parsed (it is loaded in <head>), so the
// attribute is on <html> before the body paints and there is no light flash.
applyTheme(prefersDarkTheme());
document.addEventListener("DOMContentLoaded", () => {
  updateThemeIcon(document.documentElement.getAttribute("data-theme") === "dark");
  const btn = document.getElementById("themeToggle");
  if (btn && !btn.dataset.themeBound) {
    btn.dataset.themeBound = "1";
    btn.addEventListener("click", toggleTheme);
  }
});

/*
 * Cross-page transition. Pages opting in carry class "page-fade" on <body>
 * (see main.css): they fade in on load, and navigateWithFade() fades them out
 * before handing over, so moving between feed and profile reads as one motion
 * instead of a white flash.
 */
function navigateWithFade(url) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || !document.body.classList.contains("page-fade")) {
    window.location.href = url;
    return;
  }
  document.body.classList.add("page-leaving");
  // Fall back to navigating anyway if the transition never fires.
  setTimeout(() => { window.location.href = url; }, 160);
}

// Restoring from the back/forward cache replays neither load nor transitionend,
// so a page faded out on the way to another URL would come back invisible.
window.addEventListener("pageshow", () => {
  document.body.classList.remove("page-leaving");
});

function navigateToCreateEntry() {
navigateWithFade("/entries/create/");
}

function navigateToProfile(username) {
navigateWithFade(`/authors/${username}/settings/`);
}

function navigateToPublicProfile(username) {
navigateWithFade(`/authors/${username}/`);
}

function navigateToHome() {
navigateWithFade("/home/");
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