// Smooth scrolling and scroll-linked motion (Locomotive Scroll on top of Lenis).
// Skipped entirely for people who ask for reduced motion; the page works the same without it.

import LocomotiveScroll from "locomotive-scroll";

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const ANCHOR_OFFSET = -16;
let scroll = null;

function start() {
  // CSS hides not-yet-revealed sections only under this class, so content still shows if
  // this script never runs.
  document.documentElement.classList.add("has-motion");
  scroll = new LocomotiveScroll({ lenisOptions: { lerp: 0.1 } });
}

function stop() {
  scroll?.destroy();
  scroll = null;
  document.documentElement.classList.remove("has-motion");
}

// In-page links glide instead of jumping, and don't overwrite the shareable series hash.
for (const link of document.querySelectorAll('a[href^="#"]:not([href="#"])')) {
  link.addEventListener("click", (event) => {
    const target = document.querySelector(link.getAttribute("href"));
    if (!target) return;
    event.preventDefault();
    if (scroll) scroll.scrollTo(target, { offset: ANCHOR_OFFSET });
    else target.scrollIntoView();
  });
}

reduceMotion.addEventListener("change", () => (reduceMotion.matches ? stop() : start()));
if (!reduceMotion.matches) start();
