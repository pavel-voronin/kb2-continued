'use strict';

class ChangelogWindow {
  static previewHighlight = false;

  static hasUnseenVersion(version, lastViewed) {
    if(version===lastViewed)return false;
    if (!/^\d+\.\d+\.\d+$/.test(lastViewed || '')) return true;
    const current = version.split('.').map(Number);
    const previous = lastViewed.split('.').map(Number);
    for (let i = 0; i < 3; i++) {
      if (current[i] !== previous[i]) return current[i] > previous[i];
    }
    return false;
  }

  static ageLabel(date, today = new Date()) {
    const [year, month, day] = date.split('-').map(Number);
    const currentDay = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
    const releaseDay = Date.UTC(year, month - 1, day);
    const days = Math.max(0, Math.round((currentDay - releaseDay) / 86400000));
    return days === 0 ? 'сегодня' : days === 1 ? 'вчера' : `${days}д назад`;
  }

  constructor({ button, dialog, canvas, closeButton, data, onOpen, onClose }) {
    this.button = button;
    this.dialog = dialog;
    this.canvas = canvas;
    this.context = canvas.getContext('2d', { alpha: false });
    this.closeButton = closeButton;
    this.data = data;
    this.onOpen = onOpen;
    this.onClose = onClose;
    this.open = false;
    this.offset = 0;
    this.rows = 22;
    this.font = Uint8Array.from(atob(data.font), character => character.charCodeAt(0));
    const decoder = new TextDecoder('ibm866');
    this.codes = new Map();
    for (let code = 0; code < 240; code++) this.codes.set(decoder.decode(Uint8Array.of(code)), code);
    this.lines = this.wrap(data.markdown);
    dialog.setAttribute('aria-label', 'История версий');
    dialog.querySelector('.changelog-text').textContent = data.markdown;
    button.textContent = 'Обновление: ' + ChangelogWindow.ageLabel(data.date);
    this.viewedKey = 'kb2.changelog.lastViewedVersion';
    this.lastViewed = null;
    try { this.lastViewed = localStorage.getItem(this.viewedKey); }
    catch { /* Storage can be disabled; viewing still works for this session. */ }
    this.updateUnread();
    window.addEventListener('storage', event => {
      if (event.key !== this.viewedKey && event.key !== null) return;
      this.lastViewed = event.newValue;
      this.updateUnread();
    });
    button.addEventListener('click', () => this.open ? this.hide() : this.show());
    closeButton.addEventListener('click', () => this.hide());
    dialog.addEventListener('wheel', event => {
      if (!this.open) return;
      event.preventDefault();
      this.scroll(Math.sign(event.deltaY) * 3);
    }, { passive: false });
    window.addEventListener('keydown', event => {
      if (!this.open || event.code === 'F11' || event.code === 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (document.querySelector('.toolbar').contains(event.target)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.code === 'Escape' || (event.target === closeButton && (event.code === 'Enter' || event.code === 'Space'))) this.hide();
      else if (event.code === 'ArrowDown') this.scroll(1);
      else if (event.code === 'ArrowUp') this.scroll(-1);
      else if (event.code === 'PageDown' || event.code === 'Space') this.scroll(this.rows - 1);
      else if (event.code === 'PageUp') this.scroll(1 - this.rows);
      else if (event.code === 'Home') this.scroll(-this.lines.length);
      else if (event.code === 'End') this.scroll(this.lines.length);
    }, true);
  }

  updateUnread() {
    const unread = ChangelogWindow.hasUnseenVersion(this.data.version, this.lastViewed);
    this.button.classList.toggle('has-update', ChangelogWindow.previewHighlight || unread);
    this.button.classList.toggle('preview-update', ChangelogWindow.previewHighlight);
    this.button.setAttribute('aria-label', this.button.textContent + (unread ? ', есть непросмотренные изменения' : ''));
  }

  markViewed() {
    this.lastViewed = this.data.version;
    try { localStorage.setItem(this.viewedKey, this.lastViewed); }
    catch { /* Keep the read state in memory if persistent storage is unavailable. */ }
    this.updateUnread();
  }

  wrap(markdown) {
    const lines = [];
    for (const original of markdown.replace(/\r/g, '').split('\n')) {
      if (/^#\s/.test(original)) continue;
      let line = original.replace(/^#{2,6}\s+/, '').replace(/^\s*[-*]\s+/, '* ')
        .replace(/[—–]/g, '-').replace(/[«»“”]/g, '"');
      while (line.length > 68) {
        let cut = line.lastIndexOf(' ', 68);
        if (cut < 1) cut = 68;
        lines.push(line.slice(0, cut));
        line = line.slice(cut).trimStart();
      }
      lines.push(line);
    }
    while (lines.length && !lines[0]) lines.shift();
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    return lines;
  }

  setMode(mode) {
    this.button.hidden = mode !== 'continued';
    if (this.button.hidden) this.hide();
  }

  show() {
    if (this.open || this.button.hidden) return;
    this.open = true;
    this.offset = 0;
    this.onOpen();
    this.dialog.hidden = false;
    this.draw();
    this.markViewed();
    this.closeButton.focus({ preventScroll: true });
  }

  hide() {
    if (!this.open) return;
    this.open = false;
    this.dialog.hidden = true;
    this.onClose();
  }

  scroll(rows) {
    this.offset = Math.max(0, Math.min(Math.max(0, this.lines.length - this.rows), this.offset + rows));
    this.draw();
  }

  text(text, x, y) {
    this.context.fillStyle = '#fff';
    for (const original of text) {
      const character = original === 'ё' ? 'е' : original === 'Ё' ? 'Е' : original;
      const code = this.codes.get(character) ?? this.codes.get('?');
      for (let row = 0; row < 8; row++) {
        const bits = this.font[code * 8 + row];
        for (let column = 0; column < 8; column++) {
          if (bits & (128 >> column)) this.context.fillRect(x + column, y + row, 1, 1);
        }
      }
      x += 8;
    }
  }

  draw() {
    const ctx = this.context;
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 600, 330);
    ctx.fillStyle = '#fff'; ctx.fillRect(4, 3, 593, 323);
    ctx.fillStyle = '#aaa'; ctx.fillRect(6, 5, 589, 319);
    ctx.fillStyle = '#000'; ctx.fillRect(8, 7, 585, 315);
    ctx.fillStyle = '#aaa'; ctx.fillRect(8, 28, 585, 2);
    this.text('История версий', 16, 14);
    this.text('[Закрыть]', 504, 14);
    for (let row = 0; row < this.rows; row++) {
      const line = this.lines[this.offset + row];
      if (line !== undefined) this.text(line, 20, 40 + row * 12);
    }
    if (this.lines.length > this.rows) {
      ctx.fillStyle = '#555'; ctx.fillRect(584, 40, 3, 264);
      const height = Math.max(12, Math.floor(264 * this.rows / this.lines.length));
      const y = 40 + Math.round((264 - height) * this.offset / (this.lines.length - this.rows));
      ctx.fillStyle = '#fff'; ctx.fillRect(584, y, 3, height);
    }
  }
}
