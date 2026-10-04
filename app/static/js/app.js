// Progressive enhancement only: every page works without JavaScript.
(function () {
  // Show a busy state on forms that call the model, so nobody double-submits.
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var btn = e.submitter || form.querySelector("button[type=submit], button:not([type])");
    if (btn && btn.dataset.busy) {
      btn.dataset.label = btn.innerHTML;
      setTimeout(function () {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> ' + btn.dataset.busy;
      }, 0);
    }
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      e.preventDefault();
      if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.label || btn.innerHTML; }
    }
  });

  // Live "As a ..., I need ..., so that ..." preview on capture forms.
  function bindStory(root) {
    var role = root.querySelector("[name=role]"), need = root.querySelector("[name=need]"), outcome = root.querySelector("[name=outcome]");
    var out = root.querySelector("[data-story-preview]");
    if (!role || !need || !outcome || !out) return;
    function update() {
      var r = role.value.trim(), n = need.value.trim(), o = outcome.value.trim();
      var art = /^(a|e|i|o|hon|hour)/i.test(r) ? "an" : "a";
      out.classList.toggle("placeholder", !(r || n || o));
      out.textContent = (r || n || o) ? "As " + art + " " + (r || "…") + ", I need " + (n || "…") + ", so that " + (o || "…") + "." : out.dataset.placeholder;
    }
    [role, need, outcome].forEach(function (el) { el.addEventListener("input", update); });
    update();
  }
  document.querySelectorAll("form").forEach(bindStory);
  document.body.addEventListener("htmx:afterSwap", function (e) { e.target.querySelectorAll("form").forEach(bindStory); });

  // Sizing matrix: show the resulting size as the user picks scope/effort.
  document.querySelectorAll("[data-matrix]").forEach(function (form) {
    var matrix = JSON.parse(form.dataset.matrix), labels = JSON.parse(form.dataset.labels);
    var out = form.querySelector("[data-size-result]");
    function update() {
      var s = form.querySelector("[name=scope_level]:checked"), f = form.querySelector("[name=effort_level]:checked");
      if (s && f && out) out.textContent = labels[matrix[s.value][f.value]];
    }
    form.addEventListener("change", update);
    update();
  });

  // Copy buttons.
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var el = document.querySelector(btn.dataset.copy);
      if (!el || !navigator.clipboard) return;
      navigator.clipboard.writeText(el.innerText).then(function () {
        var t = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = t; }, 1500);
      });
    });
  });
})();
