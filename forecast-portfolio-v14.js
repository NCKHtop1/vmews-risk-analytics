(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(pointer: fine)").matches;
  const root = document.documentElement;
  const top = document.querySelector(".top");
  const backToTop = document.querySelector("#backToTop");
  const hero = document.querySelector(".hero");
  const navigation = Array.from(document.querySelectorAll(".sectionNav a"));
  const number = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const price = value => number(value)?.toLocaleString("vi-VN", { maximumFractionDigits: 0 }) || "—";
  const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, token => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[token]);

  function observeSections() {
    const panels = Array.from(document.querySelectorAll("main > .panel, main > .three, #overview > .panel, .marketTape"));

    if (!reducedMotion && "IntersectionObserver" in window) {
      const reveal = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("inView");
          reveal.unobserve(entry.target);
        }
      }, { threshold: .055, rootMargin: "0px 0px -22px 0px" });

      for (const [index, panel] of panels.entries()) {
        panel.classList.add("sectionReveal");
        if (index < 3) panel.style.transitionDelay = `${index * 55}ms`;
        reveal.observe(panel);
      }
    }

    if (!("IntersectionObserver" in window)) return;
    const anchors = navigation.map(link => document.querySelector(link.getAttribute("href"))).filter(Boolean);
    const active = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        for (const link of navigation) {
          const selected = link.getAttribute("href") === `#${entry.target.id}`;
          link.classList.toggle("active", selected);
          if (selected) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        }
      }
    }, { rootMargin: "-20% 0px -68% 0px", threshold: 0 });
    anchors.forEach(section => active.observe(section));
  }

  let scrollScheduled = false;
  function updateScroll() {
    scrollScheduled = false;
    const maximum = Math.max(1, root.scrollHeight - innerHeight);
    root.style.setProperty("--scroll-progress", `${Math.min(100, scrollY / maximum * 100)}%`);
    top?.classList.toggle("scrolled", scrollY > 22);
    backToTop?.classList.toggle("visible", scrollY > innerHeight * .7);
    if (scrollY < 40 && navigation.length) {
      navigation.forEach((link, index) => {
        link.classList.toggle("active", index === 0);
        if (index === 0) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    }
  }

  addEventListener("scroll", () => {
    if (scrollScheduled) return;
    scrollScheduled = true;
    requestAnimationFrame(updateScroll);
  }, { passive: true });

  backToTop?.addEventListener("click", () => scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" }));

  function pointerLight() {
    if (reducedMotion || !finePointer) return;
    let frame = 0;
    let latest = null;

    document.addEventListener("pointermove", event => {
      latest = event;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (!latest) return;
        root.style.setProperty("--pointer-x", `${latest.clientX}px`);
        root.style.setProperty("--pointer-y", `${latest.clientY}px`);
        const panel = latest.target.closest?.(".panel");
        if (!panel) return;
        const rectangle = panel.getBoundingClientRect();
        panel.style.setProperty("--surface-x", `${latest.clientX - rectangle.left}px`);
        panel.style.setProperty("--surface-y", `${latest.clientY - rectangle.top}px`);
      });
    }, { passive: true });
  }

  function animateHeroField() {
    const canvas = document.querySelector("#heroCanvas");
    if (!canvas || !hero || reducedMotion) return;
    const context = canvas.getContext("2d", { alpha: true });
    if (!context) return;

    const pointer = { x: -.5, y: -.5 };
    let width = 0;
    let height = 0;
    let active = true;
    let frame = 0;
    let previous = 0;
    let particles = [];

    function resize() {
      const rectangle = canvas.getBoundingClientRect();
      width = rectangle.width;
      height = rectangle.height;
      if (width < 20 || height < 20) return;
      const density = Math.min(devicePixelRatio || 1, 1.75);
      canvas.width = Math.round(width * density);
      canvas.height = Math.round(height * density);
      context.setTransform(density, 0, 0, density, 0, 0);
      const count = width < 720 ? 25 : 47;
      particles = Array.from({ length: count }, (_, index) => {
        const seed = (index * 2654435761 >>> 0) / 4294967295;
        return {
          x: (index * 67.1 + seed * 137) % width,
          y: (index * 41.3 + seed * 79) % height,
          vx: (.17 + seed * .28) * (index % 2 ? 1 : -1),
          vy: (.10 + (1 - seed) * .16) * (index % 3 ? 1 : -1),
          radius: 1.0 + seed * 1.65,
        };
      });
    }

    function paint(timestamp = 0) {
      frame = 0;
      if (!active || document.hidden || !width || !height) return;
      const elapsed = Math.min(2.1, Math.max(.6, (timestamp - previous) / 16.7 || 1));
      previous = timestamp;
      context.clearRect(0, 0, width, height);

      for (const particle of particles) {
        particle.x = (particle.x + particle.vx * elapsed + width) % width;
        particle.y = (particle.y + particle.vy * elapsed + height) % height;
      }

      for (let i = 0; i < particles.length; i += 1) {
        const point = particles[i];
        for (let j = i + 1; j < particles.length; j += 1) {
          const peer = particles[j];
          const distance = Math.hypot(point.x - peer.x, point.y - peer.y);
          if (distance > 126) continue;
          context.strokeStyle = `rgba(168,235,101,${(1 - distance / 126) * .15})`;
          context.lineWidth = .75;
          context.beginPath();
          context.moveTo(point.x, point.y);
          context.lineTo(peer.x, peer.y);
          context.stroke();
        }

        const proximity = pointer.x < 0 ? 0 : Math.max(0, 1 - Math.hypot(point.x - pointer.x, point.y - pointer.y) / 145);
        context.fillStyle = `rgba(181,241,123,${.34 + proximity * .5})`;
        context.beginPath();
        context.arc(point.x, point.y, point.radius + proximity * 1.5, 0, Math.PI * 2);
        context.fill();
      }

      frame = requestAnimationFrame(paint);
    }

    hero.addEventListener("pointermove", event => {
      const rectangle = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rectangle.left;
      pointer.y = event.clientY - rectangle.top;
    }, { passive: true });
    hero.addEventListener("pointerleave", () => { pointer.x = -1; pointer.y = -1; }, { passive: true });

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(entries => {
        active = entries[0]?.isIntersecting ?? true;
        if (active && !frame) frame = requestAnimationFrame(paint);
        if (!active && frame) { cancelAnimationFrame(frame); frame = 0; }
      }, { threshold: 0 }).observe(hero);
    }

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && active && !frame) frame = requestAnimationFrame(paint);
    });
    addEventListener("resize", resize, { passive: true });
    resize();
    frame = requestAnimationFrame(paint);
  }

  function drawSparkline(base, symbol) {
    const canvas = document.querySelector("#heroSpark");
    const label = document.querySelector("#sparkSymbol");
    if (!canvas) return;
    if (label) label.textContent = symbol;
    const history = (base?.dash?.charts?.[symbol] || []).slice(-32);
    if (history.length < 2) return;

    const rectangle = canvas.getBoundingClientRect();
    const width = rectangle.width;
    const height = rectangle.height;
    const density = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    const context = canvas.getContext("2d");
    context.setTransform(density, 0, 0, density, 0, 0);
    context.clearRect(0, 0, width, height);

    const values = history.map(row => number(row.close)).filter(value => value !== null);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = maximum - minimum || 1;
    const positionX = index => 3 + index * (width - 8) / (values.length - 1);
    const positionY = value => 5 + (maximum - value) / span * (height - 11);
    const gradient = context.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "rgba(168,235,101,.22)");
    gradient.addColorStop(1, "rgba(168,235,101,0)");

    context.beginPath();
    values.forEach((value, index) => index ? context.lineTo(positionX(index), positionY(value)) : context.moveTo(positionX(index), positionY(value)));
    context.lineTo(positionX(values.length - 1), height);
    context.lineTo(positionX(0), height);
    context.closePath();
    context.fillStyle = gradient;
    context.fill();
    context.beginPath();
    values.forEach((value, index) => index ? context.lineTo(positionX(index), positionY(value)) : context.moveTo(positionX(index), positionY(value)));
    context.strokeStyle = "#a8eb65";
    context.lineWidth = 1.65;
    context.lineJoin = "round";
    context.stroke();
    context.fillStyle = "#d9ffb4";
    context.beginPath();
    context.arc(positionX(values.length - 1), positionY(values.at(-1)), 2.8, 0, Math.PI * 2);
    context.fill();
  }

  function renderMarketTape(base) {
    const track = document.querySelector("#tapeTrack");
    if (!track || !base?.dash?.symbols) return;
    const preferred = ["FPT", "VCB", "HPG", "MBB", "FRT", "PNJ", "VNM", "SSI", "GEE", "TCB", "ACB", "VIC"];
    const fragments = preferred.flatMap(symbol => {
      const snapshot = base.dash.symbols[symbol];
      const rows = base.dash.charts?.[symbol] || [];
      if (!snapshot || rows.length < 2) return [];
      const previous = number(rows.at(-2)?.rawClose ?? rows.at(-2)?.close);
      const current = number(snapshot.close);
      if (previous === null || previous <= 0 || current === null) return [];
      const change = (current / previous - 1) * 100;
      const direction = change >= 0 ? "up" : "down";
      return [`<span class="tapeQuote"><b>${escapeHTML(symbol)}</b><span>${price(current)}</span><span class="${direction}">${change >= 0 ? "+" : ""}${change.toFixed(2)}%</span></span>`];
    });
    if (!fragments.length) return;
    track.innerHTML = `${fragments.join("")}${fragments.join("")}`;
  }

  function updateSymbolPresentation(base) {
    const symbol = String(document.querySelector("#symbol")?.value || new URLSearchParams(location.search).get("symbol") || "FPT").trim().toUpperCase();
    drawSparkline(base, symbol);
    for (const button of document.querySelectorAll("#quick button")) {
      button.classList.toggle("active", button.textContent.trim() === symbol);
    }

    if (!reducedMotion) {
      for (const element of document.querySelectorAll(".stat b, .forecastCard strong")) {
        element.animate?.([
          { opacity: .48, transform: "translateY(5px)" },
          { opacity: 1, transform: "translateY(0)" },
        ], { duration: 420, easing: "cubic-bezier(.22,1,.36,1)" });
      }
    }
  }

  function enhanceLiveData() {
    const loader = window.__VMEWS_LOAD_BASE__;
    if (typeof loader !== "function") return;

    loader().then(base => {
      document.body.classList.add("appLoaded");
      renderMarketTape(base);
      const suggestions = document.querySelector("#symbolSuggestions");
      if (suggestions) {
        const fragment = document.createDocumentFragment();
        Object.keys(base.dash?.symbols || {}).sort().forEach(symbol => {
          const option = document.createElement("option");
          option.value = symbol;
          fragment.append(option);
        });
        suggestions.replaceChildren(fragment);
      }

      const status = document.querySelector("#status");
      if (status && "MutationObserver" in window) {
        new MutationObserver(() => requestAnimationFrame(() => updateSymbolPresentation(base)))
          .observe(status, { childList: true, characterData: true, subtree: true });
      }
      requestAnimationFrame(() => updateSymbolPresentation(base));
      addEventListener("resize", () => drawSparkline(base, String(document.querySelector("#symbol")?.value || "FPT").toUpperCase()), { passive: true });
    }).catch(() => {
      // The production gate and its visible error state remain authoritative.
    });
  }

  addEventListener("keydown", event => {
    const input = document.querySelector("#symbol");
    if (!input || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (event.key === "/" && target !== input && !target?.isContentEditable) {
      event.preventDefault();
      input.focus();
      input.select();
    } else if (event.key === "Escape" && target === input) {
      input.blur();
    }
  });

  observeSections();
  pointerLight();
  animateHeroField();
  enhanceLiveData();
  updateScroll();
})();
