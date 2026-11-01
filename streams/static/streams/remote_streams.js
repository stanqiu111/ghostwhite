/* Connected-node discovery stays on our origin; node passwords stay server-side. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-streams-url]').forEach(section => {
    const status = section.querySelector('[role="status"]');
    const grid = section.querySelector('.streams-grid');
    const retry = section.querySelector('button');
    async function load() {
      retry.hidden = true;
      status.textContent = 'Loading remote streams…';
      try {
        const response = await fetch(section.dataset.streamsUrl, { credentials: 'same-origin' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Remote streams are unavailable.');
        grid.replaceChildren();
        const items = data.items.filter(item => item.status === 'live');
        for (const item of items) {
          const card = document.createElement('a');
          card.className = 'stream-card';
          card.href = item.watchUrl;
          const title = document.createElement('h3');
          title.className = 'stream-card-title'; title.textContent = item.title;
          const creator = document.createElement('p');
          creator.className = 'stream-card-meta'; creator.textContent = item.owner.displayName;
          const state = document.createElement('span');
          state.className = 'stream-card-meta'; state.textContent = 'Open room';
          card.append(title, creator, state); grid.appendChild(card);
        }
        status.textContent = items.length ? 'Connected node · choose a room to watch' : 'No open streams on this node.';
      } catch (error) {
        status.textContent = error.message || 'Remote streams are unavailable.';
        retry.hidden = false;
      }
    }
    retry.addEventListener('click', load);
    load();
  });
});
