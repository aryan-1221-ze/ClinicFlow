(function () {
  'use strict';
  var token = document.querySelector('meta[name="csrf-token"]').content;
  var uid = 0;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function errorBox(message) {
    var box = el('div', 'flash flash-error', message);
    box.setAttribute('role', 'alert');
    return box;
  }

  function copyText(textarea, status) {
    var done = function () { status.textContent = 'Copied to clipboard.'; };
    var failed = function () { status.textContent = 'Copy failed. Select the text and copy it manually.'; };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(textarea.value).then(done, failed);
    } else {
      textarea.select();
      try { document.execCommand('copy') ? done() : failed(); } catch (e) { failed(); }
    }
  }

  function render(out, data, kind) {
    var frag = document.createDocumentFragment();
    frag.appendChild(el('div', 'prov prov-' + (data.source === 'llm' ? 'llm' : 'fallback'), data.label));
    if (data.notices && data.notices.length) {
      var list = el('ul', 'ai-notes');
      data.notices.forEach(function (n) { list.appendChild(el('li', '', n)); });
      frag.appendChild(list);
    }
    if (data.category) {
      frag.appendChild(el('p', 'ai-category', 'Category: ' + data.category));
    }
    if (kind === 'categorize') {
      if (data.text) frag.appendChild(el('p', 'muted', data.text));
    } else if (data.text) {
      var id = 'draft-' + (++uid);
      var wrap = el('div', 'field');
      var label = el('label', '', 'Draft (editable)');
      label.setAttribute('for', id);
      var area = el('textarea');
      area.id = id; area.rows = 9; area.value = data.text;
      wrap.appendChild(label); wrap.appendChild(area);
      frag.appendChild(wrap);
      var status = el('span', 'muted');
      status.setAttribute('role', 'status');
      var copy = el('button', 'btn', 'Copy draft');
      copy.type = 'button';
      copy.addEventListener('click', function () { copyText(area, status); });
      var row = el('div', 'form-actions'); row.appendChild(copy); row.appendChild(status);
      frag.appendChild(row);
      frag.appendChild(el('p', 'ai-warn', 'Draft only. Review and edit before use. ClinicFlow does not send messages.'));
    }
    out.replaceChildren(frag);
  }

  document.querySelectorAll('form.ai-form').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var out = form.parentElement.querySelector('.ai-result');
      var button = form.querySelector('button[type="submit"]');
      var label = button.textContent;
      var body = {};
      new FormData(form).forEach(function (value, key) { body[key] = value; });

      button.disabled = true;
      button.textContent = 'Working...';
      out.setAttribute('aria-busy', 'true');
      out.replaceChildren(el('p', 'muted', 'Working on it...'));

      fetch(form.dataset.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify(body)
      }).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) {
          if (!res.ok || !data) {
            out.replaceChildren(errorBox((data && data.error) || 'The request failed. Reload the page and try again.'));
          } else {
            render(out, data, form.dataset.kind);
          }
        });
      }).catch(function () {
        out.replaceChildren(errorBox('Could not reach the server. Check your connection and try again.'));
      }).then(function () {
        button.disabled = false;
        button.textContent = label;
        out.removeAttribute('aria-busy');
      });
    });
  });
})();
