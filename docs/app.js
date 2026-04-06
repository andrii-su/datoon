const metricEls = document.querySelectorAll("[data-target]");

const animateMetric = (el) => {
    const target = Number(el.dataset.target);
    const suffix = el.dataset.suffix ?? "";
    if (!Number.isFinite(target)) {
        return;
    }

    let frame = 0;
    const frames = 40;
    const tick = () => {
        frame += 1;
        const progress = frame / frames;
        const eased = 1 - (1 - progress) ** 3;
        const current = target * eased;

        if (suffix === "%") {
            el.textContent = `${current.toFixed(1)}${suffix}`;
        } else {
            el.textContent = `${Math.round(current)}${suffix}`;
        }

        if (frame < frames) {
            requestAnimationFrame(tick);
        }
    };

    requestAnimationFrame(tick);
};

const observer = new IntersectionObserver(
    (entries, obs) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) {
                return;
            }
            animateMetric(entry.target);
            obs.unobserve(entry.target);
        });
    },
    { threshold: 0.4 },
);

metricEls.forEach((el) => observer.observe(el));

const year = document.querySelector("[data-year]");
if (year) {
    year.textContent = new Date().getFullYear().toString();
}
