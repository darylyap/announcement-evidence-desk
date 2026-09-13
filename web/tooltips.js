function helpTip(text, label = "Help") {
  return `<button type="button" class="help-trigger" data-help="${esc(text)}" aria-label="${esc(label)}">${esc(label)} <span aria-hidden="true">ⓘ</span></button>`;
}
document.addEventListener("DOMContentLoaded", () => {
  const tip = document.createElement("div");
  tip.id = "helpTooltip";
  tip.setAttribute("role", "tooltip");
  tip.setAttribute("popover", "manual");
  document.body.append(tip);
  let active = null,
    timer;
  function hide() {
    clearTimeout(timer);
    tip.hidePopover();
    active?.removeAttribute("aria-describedby");
    active = null;
  }
  function show(button) {
    clearTimeout(timer);
    if (active && active !== button) active.removeAttribute("aria-describedby");
    const parent = button.closest("dialog") || document.body;
    if (tip.parentElement !== parent) {
      tip.hidePopover();
      parent.append(tip);
    }
    active = button;
    tip.textContent = button.dataset.help;
    button.setAttribute("aria-describedby", tip.id);
    tip.showPopover();
    const rect = button.getBoundingClientRect();
    const width = tip.offsetWidth,
      height = tip.offsetHeight;
    tip.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - width - 12))}px`;
    tip.style.top = `${Math.max(12, rect.bottom + height + 12 < innerHeight ? rect.bottom + 8 : rect.top - height - 8)}px`;
  }
  function deferHide() {
    timer = setTimeout(hide, 150);
  }
  document.addEventListener("pointerover", (e) => {
    if (tip.contains(e.target)) return clearTimeout(timer);
    const button = e.target.closest("[data-help]");
    if (button) show(button);
  });
  document.addEventListener("pointerout", (e) => {
    if (e.target.closest("[data-help]") || tip.contains(e.target)) deferHide();
  });
  document.addEventListener("focusin", (e) => {
    const button = e.target.closest("[data-help]");
    if (button) show(button);
    else hide();
  });
  document.addEventListener("focusout", deferHide);
  document.addEventListener("click", (e) => {
    const button = e.target.closest("[data-help]");
    if (button) show(button);
    else if (!tip.contains(e.target)) hide();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && active) {
      e.preventDefault();
      e.stopPropagation();
      hide();
    }
  });
  document.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);
});
