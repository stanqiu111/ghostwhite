// Whole-site rendered theme/layout audit against the runner's isolated database.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const output = path.join(config.output, 'frontend');
fs.mkdirSync(output, { recursive: true });

async function audit(page) {
  return page.evaluate(() => {
    const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
    const luminance = values => values.slice(0, 3).map(v => v / 255)
      .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const background = element => {
      if (!element) return [255, 255, 255];
      const color = rgb(getComputedStyle(element).backgroundColor);
      if (color.length === 3 || color[3] === 1) return color;
      const parent = background(element.parentElement);
      return parent.map((v, i) => (color[i] || 0) * (color[3] || 0) + v * (1 - (color[3] || 0)));
    };
    const visible = el => {
      const box = el.getBoundingClientRect(), style = getComputedStyle(el);
      return box.width > 0 && box.height > 0 && style.visibility === 'visible'
        && Number(style.opacity) > 0 && !el.closest('[hidden], [aria-hidden="true"], script, style, svg');
    };
    const label = el => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : el.className ? '.' + String(el.className).trim().replace(/\s+/g, '.') : ''}`;
    const contrast = [];
    for (const el of document.querySelectorAll('body *')) {
      if (!visible(el) || el.matches(':disabled') || el.closest('button:disabled')) continue;
      const text = [...el.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('').trim();
      if (text.length < 2) continue;
      const style = getComputedStyle(el);
      // Fixed media/code artwork has its own intentional palette; gradients
      // require visual review rather than this solid-background calculation.
      if (style.backgroundImage !== 'none' || el.closest('.wire, .code-window, pre')) continue;
      const fg = luminance(rgb(style.color)), bg = luminance(background(el));
      const ratio = (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05);
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
      if (ratio + .02 < (large ? 3 : 4.5)) contrast.push({ element: label(el), text: text.slice(0, 45), ratio: +ratio.toFixed(2) });
    }
    const overflow = document.documentElement.scrollWidth > innerWidth;
    const spilling = overflow ? [...document.querySelectorAll('body *')].filter(el => visible(el)
      && el.getBoundingClientRect().right > innerWidth + 2 && !el.closest('.table-wrap, .stream-chat-messages'))
      .slice(0, 8).map(label) : [];
    return { overflow, spilling, contrast: contrast.slice(0, 30), theme: document.documentElement.dataset.theme };
  });
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
  const results = [], errors = [];
  try {
    for (const theme of ['light', 'dark']) {
      const member = await browser.newContext({ colorScheme: theme, reducedMotion: 'reduce' });
      const guest = await browser.newContext({ colorScheme: theme, reducedMotion: 'reduce' });
      for (const context of [member, guest]) {
        await context.route('https://**', route => route.abort());
        await context.addInitScript(theme => {
          if (!localStorage.getItem('theme')) localStorage.setItem('theme', theme);
          window.uiPending = 0;
          const original = window.fetch;
          window.fetch = async (...args) => {
            window.uiPending++;
            try { return await original(...args); } finally { window.uiPending--; }
          };
        }, theme);
      }
      const login = await member.request.post(config.base + '/api/authors/login/', {
        data: { username: 'media-owner', password: config.password },
      });
      assert.equal(login.status(), 200);
      const identity = await login.json();
      await member.addInitScript(identity => {
        localStorage.setItem('access_token', identity.access);
        localStorage.setItem('refresh_token', identity.refresh);
        localStorage.setItem('user_id', identity.user_id);
        localStorage.setItem('username', 'media-owner');
      }, identity);
      const cases = [
        ['landing', '/', guest], ['network', '/network/', guest], ['login', '/authors/auth/', guest],
        ['verification', '/authors/verify-email/invalid-preview/', guest],
        ['feed', '/home/', member], ['profile', '/authors/media-owner/settings/', member],
        ['public-profile', '/authors/media-viewer-0/', member], ['settings', '/authors/settings/', member],
        ['nodes', '/authors/remote-nodes/', member], ['staff', '/authors/staff/', member],
        ['compose', '/entries/create/', member], ['entry', `/entries/${config.frontend.entry}/`, member],
        ['inbox', '/inbox/', member], ['streams', '/streams/', member],
        ['stream-create', '/streams/create/', member], ['studio', config.path, member],
        ['remote-error', `/streams/remote/${config.frontend.remoteNode}/00000000-0000-0000-0000-000000000001/`, member, 503],
      ];
      for (const [name, url, context, expected = 200] of cases) {
        const page = await context.newPage();
        page.on('pageerror', error => errors.push({ name, theme, error: error.message }));
        const response = await page.goto(config.base + url);
        assert.equal(response.status(), expected, name);
        assert.match(await page.locator('meta[name="viewport"]').getAttribute('content'), /width=device-width/, `${name} uses the device viewport`);
        await page.waitForFunction(() => window.uiPending === 0);
        for (const width of [1440, 390]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          const result = { name, theme, width, ...await audit(page) };
          results.push(result);
          await page.screenshot({ path: path.join(output, `${name}-${theme}-${width}.png`), fullPage: true, animations: 'disabled' });
        }
        // Exercise the actual enabled controls as well as their default render.
        const hoverTargets = {
          feed: ['.follow-btn', '#markAllReadBtn'],
          profile: ['#saveBtn'], 'public-profile': ['.followBtn'],
          entry: ['.btn-like', '.btn-edit', '.btn-delete', '.delete_button', '.edit_button'],
          compose: ['#postBtn', '#tabPreview'], settings: ['.save-btn'],
          login: ['.login-button', '.signup-button'], 'stream-create': ['.stream-btn'],
        };
        for (const selector of hoverTargets[name] || []) {
          const control = page.locator(selector).first();
          if (!(await control.isVisible()) || !(await control.isEnabled())) continue;
          await control.hover();
          results.push({ name: `${name}-hover-${selector}`, theme, width: 390, ...await audit(page) });
          await control.focus();
          assert.notEqual(await control.evaluate(el => getComputedStyle(el).outlineStyle), 'none', `${name} ${selector} focus`);
        }
        if (name === 'nodes') {
          assert.match(await page.locator('.node-item').filter({ hasText: 'https://disabled-peer.example.test/' }).textContent(), /Connection enabled:\s*No/);
          const control = page.locator('.follow-btn').first();
          // Synthetic visual states, not claims of remote follow delivery.
          for (const state of ['follow', 'unfollow', 'pending']) {
            await control.evaluate((el, state) => { el.className = `follow-btn ${state}`; el.textContent = state; }, state);
            await control.hover();
            results.push({ name: `nodes-${state}-hover`, theme, width: 390, ...await audit(page) });
          }
        }
        if (name === 'login') {
          await page.locator('#error-message').evaluate(el => { el.textContent = 'Please check your details and try again.'; el.style.display = 'block'; });
          results.push({ name: 'login-error', theme, width: 390, ...await audit(page) });
        }
        if (name === 'compose') {
          await page.locator('#contentArea').fill('**Readable preview** <img src="x" onerror="window.previewExecuted=true"><script>window.previewExecuted=true</script>\n\n~~Old wording~~\n\n| First | Second |\n| --- | --- |\n| One | Two |');
          await page.locator('#tabPreview').click();
          assert.equal(await page.locator('#preview strong').textContent(), 'Readable preview');
          assert.equal(await page.locator('#preview [onerror], #preview script').count(), 0);
          assert.equal(await page.locator('#preview del').textContent(), 'Old wording');
          assert.equal(await page.locator('#preview table td').count(), 2, 'safe GFM formatting survives sanitization');
          assert.equal(await page.evaluate(() => !!window.previewExecuted), false);
          results.push({ name: 'compose-preview', theme, width: 390, ...await audit(page) });
          await page.locator('#tabEdit').click();
          await page.locator('#contentArea').waitFor({ state: 'visible' });
          assert.equal(await page.locator('#preview').isVisible(), false);
          const fallbackSafe = await page.evaluate(() => {
            const purifier = window.DOMPurify;
            try {
              window.DOMPurify = undefined;
              const node = document.createElement('div');
              node.innerHTML = renderSafeMarkdown('<img src=x onerror=alert(1)>');
              return node.children.length === 0 && node.textContent === '<img src=x onerror=alert(1)>';
            } finally { window.DOMPurify = purifier; }
          });
          assert.equal(fallbackSafe, true, 'missing sanitizer falls back to text');
        }
        if (name === 'entry') {
          await page.locator('#copyChip').waitFor({ state: 'visible' });
          await page.locator('#tabLikes').click();
          await page.locator('#likesList').waitFor({ state: 'visible' });
          assert.equal(await page.locator('#commentsList').isVisible(), false);
          await page.locator('#tabComments').click();
          await page.locator('.btn-edit').click();
          await page.locator('.comment-edit:not([hidden])').fill(`Edited in ${theme} mode.`);
          results.push({ name: 'comment-edit', theme, width: 390, ...await audit(page) });
          await page.locator('.btn-save:not([hidden])').click();
          await page.waitForFunction(text => [...document.querySelectorAll('.comment-body')].some(el => el.textContent === text), `Edited in ${theme} mode.`);
          assert.equal(await page.locator('.comment-edit:not([hidden])').count(), 0);
          await page.evaluate(() => renderEntry({ ...ENTRY, contentType: 'text/markdown', content_type: 'text/markdown', content: '**Safe entry** <img src=x onerror="window.entryExecuted=true">' }));
          assert.equal(await page.locator('#entryContent [onerror]').count(), 0);
          assert.equal(await page.locator('#entryContent strong').textContent(), 'Safe entry');
          assert.equal(await page.evaluate(() => !!window.entryExecuted), false);
        }
        await page.close();
      }
      await member.close(); await guest.close();
    }
    const preferences = await browser.newContext({ colorScheme: 'dark', reducedMotion: 'reduce' });
    await preferences.route('https://**', route => route.abort());
    const first = await preferences.newPage();
    await first.goto(config.base + '/network/');
    await first.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    await first.emulateMedia({ colorScheme: 'light' });
    await first.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    await first.locator('#themeToggle').click();
    await first.reload();
    assert.equal(await first.locator('html').getAttribute('data-theme'), 'dark', 'explicit choice survives reload and light OS');
    const second = await preferences.newPage();
    await second.goto(config.base + '/network/');
    await first.locator('#themeToggle').click();
    await second.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    await first.keyboard.press('Tab');
    await first.locator('#themeToggle').focus();
    assert.notEqual(await first.locator('#themeToggle').evaluate(el => getComputedStyle(el).outlineStyle), 'none');
    assert.equal(await first.locator('#themeToggle').getAttribute('aria-label'), 'Switch to dark mode');
    await preferences.close();
    fs.writeFileSync(path.join(output, 'audit.json'), JSON.stringify({ results, errors }, null, 2));
    const failures = results.filter(result => result.overflow || result.contrast.length);
    console.log(JSON.stringify({ renderedCases: results.length, failingCases: failures.length, pageErrors: errors, screenshots: output }));
    if (!config.audit) {
      assert.deepEqual(errors, [], 'no browser script errors');
      assert.equal(failures.length, 0, `theme/layout findings: see ${output}/audit.json`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
