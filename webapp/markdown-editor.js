export function renderMarkdown(md) {
  // minimal placeholder – replace with your real renderer (e.g., marked/markdown-it)
  return md.replaceAll(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}
