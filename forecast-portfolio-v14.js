(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const panels = Array.from(document.querySelectorAll("main > .panel, main > .three"));

  if (!reducedMotion && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("inView");
          observer.unobserve(entry.target);
        }
      }
    }, { threshold: .08, rootMargin: "0px 0px -24px 0px" });

    for (const panel of panels) {
      panel.classList.add("sectionReveal");
      observer.observe(panel);
    }
  }

  let scheduled = false;
  function updateProgress() {
    scheduled = false;
    const maximum = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    document.documentElement.style.setProperty("--scroll-progress", `${Math.min(100, scrollY / maximum * 100)}%`);
  }

  addEventListener("scroll", () => {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(updateProgress);
    }
  }, { passive: true });

  updateProgress();
})();
