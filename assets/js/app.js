/* Ad Dimensions Toolkit: renders platform cards from window.HUB_DATA (see scripts/generate_templates.py). */
(function () {
  "use strict";
  var D = window.HUB_DATA;
  if (!D) {
    document.getElementById("list-digital").textContent = "Data failed to load (data/hub-data.js).";
    return;
  }
  var REPO = "https://github.com/blockiie-daduck/adv-dimensions-hub";
  var PRESET = D.formats.presets;
  var FORMATS = D.formats.templateFormats;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  var CHEV = '<svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>';

  function fmtIn(n) {
    var whole = Math.floor(n + 1e-9), frac = n - whole;
    var table = [[0.125, "1/8"], [0.25, "1/4"], [0.375, "3/8"], [0.5, "1/2"], [0.625, "5/8"], [0.75, "3/4"], [0.875, "7/8"]];
    for (var i = 0; i < table.length; i++) {
      if (Math.abs(frac - table[i][0]) < 0.004) return (whole ? whole + " " : "") + table[i][1];
    }
    return String(Math.round(n * 100) / 100).replace(/\.0+$/, "");
  }
  function dimText(p, s) {
    return p.section === "digital" ? s.w + "×" + s.h : fmtIn(s.wIn) + "×" + fmtIn(s.hIn) + " in";
  }
  function sizeSearchText(p, s) {
    return (p.section === "digital" ? s.w + "x" + s.h : s.wIn + "x" + s.hIn) + " " + (s.label || "");
  }

  function cardMeta(p) {
    var preset = PRESET[p.section];
    var chips = [];
    var types = (p.fileTypes || []).join(", ");
    if (types) chips.push('<span class="chip type">' + esc(types) + "</span>");
    if (p.section === "digital") {
      chips.push('<span class="chip">' + esc(p.dpi || preset.dpi) + " dpi</span>");
      chips.push('<span class="chip">' + esc(p.colorProfile || "sRGB") + "</span>");
      if (p.maxFileSize) chips.push('<span class="chip">Max ' + esc(String(p.maxFileSize).split(/[;(]/)[0].trim()) + "</span>");
    } else {
      chips.push('<span class="chip">' + esc(p.dpi || preset.dpi) + " dpi</span>");
      chips.push('<span class="chip">' + esc(String(p.colorProfile || "CMYK").split("(")[0].trim()) + "</span>");
      chips.push('<span class="chip">' + (p.bleedIn ? fmtIn(p.bleedIn) + " in bleed" : "No bleed") + "</span>");
    }
    return chips.join("");
  }

  function makeCard(p) {
    var man = (D.manifest[p.id] || { sizes: [] });
    var state = { idx: 0 };
    var card = el("article", "card");
    card.id = p.id;
    card.dataset.section = p.section;

    // header (collapsible trigger)
    var head = el("button", "head");
    head.type = "button";
    head.setAttribute("aria-expanded", "false");
    head.setAttribute("aria-controls", p.id + "-panel");
    head.innerHTML =
      '<span class="logo"><img src="assets/logos/' + esc(p.logo) + '" alt="" width="28" height="28" loading="lazy"></span>' +
      '<span class="mid"><span class="name">' + esc(p.name) + "</span>" +
      '<span class="sum" style="display:block">' + esc(p.summary) + "</span>" +
      '<span class="chips">' + cardMeta(p) + "</span></span>" +
      '<span class="chev" aria-hidden="true">' + CHEV + "</span>";
    card.appendChild(head);

    var body = el("div", "body");
    var inner = el("div", "body-inner");
    var panel = el("div", "panel");
    panel.id = p.id + "-panel";
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-label", p.name + " details");
    inner.appendChild(panel);
    body.appendChild(inner);
    card.appendChild(body);

    var built = false;
    function build() {
      if (built) return;
      built = true;
      panel.innerHTML =
        '<div class="split"><div><h3>Sizes</h3><div class="tiles"></div></div><div class="dl-slot"></div></div>' +
        '<div class="info"></div><div class="meta"></div>';
      var tiles = panel.querySelector(".tiles");
      var maxSide = Math.max.apply(null, p.sizes.map(function (s) { return p.section === "digital" ? Math.max(s.w, s.h) : Math.max(s.wIn, s.hIn); }));
      p.sizes.forEach(function (s, i) {
        var w = p.section === "digital" ? s.w : s.wIn, h = p.section === "digital" ? s.h : s.hIn;
        var ratio = Math.max(w, h);
        var scale = 0.78 / ratio; // longest side = 78% of the square
        var t = el("button", "tile");
        t.type = "button";
        t.dataset.i = i;
        t.dataset.search = sizeSearchText(p, s).toLowerCase();
        t.setAttribute("aria-pressed", i === 0 ? "true" : "false");
        t.innerHTML =
          '<span class="sq"><span class="shape" style="width:' + (w * scale * 100).toFixed(1) + "%;height:" + (h * scale * 100).toFixed(1) + '%"></span>' +
          '<span class="dim">' + esc(dimText(p, s)) + "</span></span>" +
          '<span class="lab"><b>' + esc(s.label || "") + "</b></span>";
        t.addEventListener("click", function () { select(i); });
        tiles.appendChild(t);
      });
      renderInfo();
      renderMeta();
      select(0);
    }

    function select(i) {
      state.idx = i;
      panel.querySelectorAll(".tile").forEach(function (t) { t.setAttribute("aria-pressed", String(+t.dataset.i === i)); });
      renderDownload();
    }

    function renderDownload() {
      var s = p.sizes[state.idx];
      var entry = man.sizes[state.idx] || { files: [] };
      var preset = PRESET[p.section];
      var spec = [];
      spec.push(p.section === "digital" ? "RGB · " + (p.colorProfile || "sRGB") : String(p.colorProfile || preset.colorProfile));
      spec.push(entry.dpi + " dpi" + (p.section === "editorial" && entry.dpi < (p.dpi || 300) ? " (reduced scale)" : ""));
      spec.push(p.section === "digital" ? "No bleed" : (p.bleedIn ? fmtIn(p.bleedIn) + " in bleed" : "No bleed"));
      if (entry.w) spec.push("Canvas " + entry.w + "×" + entry.h + " px");
      var html = '<div class="dl"><h4>Download the template</h4><p class="sel">' + esc(p.name) + " · " + esc(s.label || "") + " · " + esc(dimText(p, s)) + "</p>" +
        '<div class="spec">' + spec.map(function (x) { return '<span class="chip">' + esc(x) + "</span>"; }).join("") + '</div><div class="files">';
      FORMATS.forEach(function (f) {
        if (f.applies.indexOf(p.section) < 0) return;
        var file = entry.files.filter(function (x) { return x.ext === f.ext; })[0];
        if (file) {
          html += '<a class="file" href="' + esc(file.path) + '" download title="' + esc(f.tools) + '">.' + esc(f.ext) + "<small>" + esc(f.label) + "</small></a>";
        } else if (f.status === "placeholder") {
          html += '<span class="file soon" title="' + esc(f.tools) + ' (coming soon)">.' + esc(f.ext) + "<small>coming soon</small></span>";
        }
      });
      html += "</div>";
      if (man.zip) html += '<a class="zip" href="' + esc(man.zip) + '" download>Download all sizes (.zip)</a>';
      var notes = [];
      notes.push("Layered files include locked guide layers: " + (p.section === "editorial" && p.bleedIn ? "Bleed, Trim, Safe Zone, Guides" : "Safe Zone, Guides") + (s.uiSafeZone ? ", Platform UI" : "") + ". Hide them before export.");
      if (s.retina2x) notes.push("Accepts 2× art: design at double size, export at 1×.");
      if (s.uiSafeZone) notes.push("Orange overlay marks areas covered by the platform interface.");
      if (s.note) notes.push(s.note);
      html += '<p class="note">' + notes.map(esc).join("<br>") + "</p></div>";
      panel.querySelector(".dl-slot").innerHTML = html;
    }

    function list(items, cls) {
      return '<ul class="' + (cls || "") + '">' + (items || []).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
    }

    function renderInfo() {
      var info = panel.querySelector(".info");
      var bp = p.bestPractices || {};
      var tabs = [["do", "Do"], ["avoid", "Avoid"], ["tips", "Creative tips"]];
      var rules = '<div class="box warn"><h3>Rules (can cause rejection)</h3>' + list(p.rules) + "</div>";
      var best = '<div class="box"><h3>Best practices</h3><div class="seg" role="tablist">' +
        tabs.map(function (t, i) { return '<button type="button" role="tab" aria-selected="' + (i === 0) + '" data-t="' + t[0] + '">' + t[1] + "</button>"; }).join("") +
        '</div><div class="bp">' + list(bp.do) + "</div></div>";
      // preflight / export checklist
      var pre = [];
      var types = (p.fileTypes || []).join(" / ");
      if (p.section === "digital") {
        pre.push("Export as " + types + " at " + (p.dpi || 72) + " dpi, " + (p.colorProfile || "sRGB"));
        if (p.maxFileSize) pre.push("Keep file size within: " + p.maxFileSize);
        if (p.gif) {
          ["maxSize:Max GIF size", "maxDuration:Max duration", "loops:Loops", "fps:Frame rate"].forEach(function (k) {
            var kk = k.split(":");
            if (p.gif[kk[0]]) pre.push(kk[1] + ": " + p.gif[kk[0]]);
          });
        }
        pre.push("Hide guide layers, then check text is legible at actual size");
      } else {
        pre.push("Export a press-ready PDF (PDF/X-1a or X-4) at " + (p.dpi || 300) + " dpi, " + String(p.colorProfile || "CMYK"));
        pre.push(p.bleedIn ? "Include " + fmtIn(p.bleedIn) + " in bleed on all sides; keep key content " + fmtIn(p.safeIn || 0.25) + " in inside trim" : "No bleed for this format; keep key content inside the safe margin");
        if (p.totalInkLimit) pre.push("Total ink limit: " + p.totalInkLimit);
        pre.push("Convert text to rich black only where the publisher allows; embed fonts or outline them");
        pre.push("Confirm every size and spec with the publication’s rate card");
      }
      var preflight = '<div class="box"><h3>Export checklist</h3>' + list(pre, "check") + "</div>";
      info.innerHTML = rules + best + preflight;
      var bpBox = info.querySelector(".bp");
      info.querySelectorAll(".seg button").forEach(function (b) {
        b.addEventListener("click", function () {
          info.querySelectorAll(".seg button").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
          bpBox.innerHTML = list(bp[b.dataset.t]);
        });
      });
    }

    function specText() {
      var s = p.sizes[state.idx];
      var lines = [p.name + " — " + p.summary, "File types: " + (p.fileTypes || []).join(", "), "Resolution: " + (p.dpi || "") + " dpi", "Color: " + (p.colorProfile || ""), "Max file size: " + (p.maxFileSize || "n/a"), "Sizes:"];
      p.sizes.forEach(function (x) { lines.push("  - " + dimText(p, x) + " " + (x.label || "")); });
      lines.push("Rules:");
      (p.rules || []).forEach(function (r) { lines.push("  - " + r); });
      lines.push("Last verified: " + p.verified + " · " + location.href.split("#")[0] + "#" + p.id);
      return lines.join("\n");
    }

    function renderMeta() {
      var m = panel.querySelector(".meta");
      var conf = String(p.confidence || "").trim();
      var level = (conf.match(/^(low-medium|medium-low|medium-high|high|medium|low)/i) || [""])[0].toLowerCase();
      var src = (p.sources || []).map(function (u) { return '<li><a href="' + esc(u) + '" rel="noopener" target="_blank">' + esc(u) + "</a></li>"; }).join("");
      m.innerHTML =
        "<span>Last verified " + esc(p.verified) + "</span>" +
        (level ? '<span class="conf-' + esc(level) + '" title="' + esc(conf) + '">Confidence: ' + esc(level) + "</span>" : "") +
        (src ? '<details class="src"><summary>Sources</summary><ul>' + src + "</ul></details>" : "") +
        '<span class="sp"></span><button type="button" class="btn copy">Copy specs</button>' +
        '<a class="btn" target="_blank" rel="noopener" href="' + REPO + "/issues/new?template=spec-update.yml&title=" + encodeURIComponent("Spec update: " + p.name) + '">Report an issue</a>';
      m.querySelector(".copy").addEventListener("click", function (e) {
        var b = e.currentTarget;
        var done = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy specs"; }, 1600); };
        if (navigator.clipboard) navigator.clipboard.writeText(specText()).then(done, done); else done();
      });
    }

    function setOpen(open) {
      card.classList.toggle("open", open);
      head.setAttribute("aria-expanded", String(open));
      if (open) build();
    }
    head.addEventListener("click", function () {
      var open = !card.classList.contains("open");
      setOpen(open);
      if (open) { try { history.replaceState(null, "", "#" + p.id); } catch (e) {} }
    });
    card._open = setOpen;
    card._select = function (needle) {
      build();
      for (var i = 0; i < p.sizes.length; i++) {
        if (sizeSearchText(p, p.sizes[i]).toLowerCase().indexOf(needle) >= 0) { select(i); return; }
      }
    };
    card._sizeTiles = function () { return panel.querySelectorAll(".tile"); };
    card._search = (p.name + " " + p.summary + " " + (p.fileTypes || []).join(" ") + " " + p.sizes.map(function (s) { return sizeSearchText(p, s); }).join(" ")).toLowerCase();
    return card;
  }

  // render
  var cards = [];
  var counts = { digital: 0, editorial: 0 };
  D.platforms.forEach(function (p) {
    var c = makeCard(p);
    document.getElementById("list-" + p.section).appendChild(c);
    cards.push(c);
    counts[p.section]++;
  });
  document.getElementById("n-digital").textContent = counts.digital;
  document.getElementById("n-editorial").textContent = counts.editorial;

  // search
  var q = document.getElementById("q");
  function norm(s) { return s.toLowerCase().replace(/\s*[x×]\s*/g, "x").replace(/\s+/g, " ").trim(); }
  function applySearch() {
    var needle = norm(q.value);
    var any = false;
    var visible = { digital: 0, editorial: 0 };
    cards.forEach(function (c) {
      var hit = !needle || norm(c._search).indexOf(needle) >= 0;
      c.hidden = !hit;
      if (hit) { any = true; visible[c.dataset.section]++; }
      if (hit && needle && /\d/.test(needle)) { c._open(true); c._select(needle); }
    });
    ["digital", "editorial"].forEach(function (s) { document.getElementById(s).hidden = !visible[s]; });
    document.getElementById("empty").hidden = any;
  }
  q.addEventListener("input", applySearch);

  // deep links
  function openFromHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    var c = id && document.getElementById(id);
    if (c && c.classList.contains("card")) {
      c._open(true);
      setTimeout(function () { c.scrollIntoView({ behavior: "smooth", block: "start" }); }, 60);
    }
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();

  // section nav highlight
  var links = document.querySelectorAll("[data-nav]");
  var secs = ["digital", "editorial"].map(function (id) { return document.getElementById(id); });
  function onScroll() {
    var cur = "digital";
    secs.forEach(function (s) { if (s.getBoundingClientRect().top < 180) cur = s.id; });
    links.forEach(function (a) { a.classList.toggle("on", a.dataset.nav === cur); });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();
