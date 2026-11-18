/* Versioned public filter links (#469). No filtering logic or HTML injection. */
function S(key, fallback) {
  var o = window.GINOT_I18N || {};
  return o[key] || fallback;
}
(function () {
  'use strict';
  var params = new URLSearchParams(location.search), adapters = {}, recognized = {};
  // Bare deep links (e.g. ?permit.pfq=2024%2F0215.00#permits) carry no
  // filters=1 marker: activate on any recognized state key then. An
  // explicit filters value of an unknown version stays inert (#469).
  function stateActive() {
    var v = params.get('filters');
    if (v !== null) return v === '1';
    return Array.from(params.keys()).some(function (k) { return recognized[k] === true; });
  }
  function dateOK(v) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
    var d = new Date(v + 'T00:00:00Z');
    return !isNaN(d) && d.toISOString().slice(0, 10) === v;
  }
  function register(name, controls, extra) {
    var defaults = {}, keys = Object.keys(controls);
    var stateKeys = keys.concat(extra.keys || []);
    stateKeys.forEach(function(k){recognized[name+'.'+k]=true;});
    keys.forEach(function (id) {
      var e = document.getElementById(id);
      defaults[id] = e.type === 'checkbox' ? e.checked : e.value;
    });
    function restore() {
      if (!stateActive()) return;
      keys.forEach(function (id) {
        var e = document.getElementById(id), v = params.get(name + '.' + id);
        if (v === null || v.length > 500) return;
        if (e.type === 'checkbox') { if (v === '0' || v === '1') e.checked = v === '1'; }
        else if (e.tagName === 'SELECT') {
          if (Array.from(e.options).some(function (o) { return o.value === v; })) e.value = v;
        } else if (e.type === 'date') { if (v === '' || dateOK(v)) e.value = v; }
        else e.value = v;
      });
      extra.restore(params, name);
    }
    adapters[name] = function (url) {
      keys.forEach(function (id) {
        var e = document.getElementById(id), v = e.type === 'checkbox' ? e.checked : e.value;
        if (v !== defaults[id]) url.searchParams.set(name + '.' + id, e.type === 'checkbox' ? (v ? '1' : '0') : v);
      });
      extra.write(url.searchParams, name);
    };
    var hasState = stateActive() && Array.from(params.keys()).some(function (k) { return stateKeys.some(function(id){return k===name+'.'+id;}); });
    return {restore: restore, hasState: hasState};
  }
  function build() {
    var url = new URL(location.href);
    Array.from(url.searchParams.keys()).forEach(function (k) {
      if (k === 'filters' || recognized[k]===true) url.searchParams.delete(k);
    });
    url.searchParams.set('filters', '1');
    Object.keys(adapters).forEach(function (k) { adapters[k](url); });
    return url.href;
  }
  function install(id) {
    var button = document.getElementById(id);
    if (!button) return;
    var fallback = document.createElement('input');
    fallback.type = 'text'; fallback.readOnly = true; fallback.hidden = true;
    fallback.setAttribute('aria-label', S('fl.aria', 'קישור לסינון הנוכחי'));
    fallback.style.maxWidth = '100%';
    var status = document.createElement('span'); status.setAttribute('role', 'status');
    button.after(fallback, status);
    button.addEventListener('click', function () {
      var link = build(); fallback.hidden = true; status.textContent = '';
      function failed() {
        fallback.value = link; fallback.hidden = false; fallback.focus(); fallback.select();
        status.textContent = S('fl.not_copied', 'לא הועתק. אפשר לבחור ולהעתיק את הקישור המוצג.');
      }
      if (!navigator.clipboard || !navigator.clipboard.writeText) { failed(); return; }
      try {
        Promise.resolve(navigator.clipboard.writeText(link)).then(function () {
          status.textContent = S('fl.copied', 'הקישור הועתק');
        }, failed);
      } catch (_) { failed(); }
    });
  }
  window.GinotFilterLinks = {register: register, build: build};
  install('copy-plan-link'); install('copy-permit-link');
})();
