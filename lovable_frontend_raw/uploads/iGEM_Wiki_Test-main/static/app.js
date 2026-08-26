// app.js - Frontend interactions and dynamic state

document.addEventListener('DOMContentLoaded', () => {
    // ── 0. Apply persisted theme (default: glass) ────────
    const THEME_LINK_ID = 'wiki-theme-css';
    const savedTheme = localStorage.getItem('wiki-theme');
    if (savedTheme && savedTheme !== 'glass') {
        const link = document.createElement('link');
        link.id = THEME_LINK_ID;
        link.rel = 'stylesheet';
        link.href = '/static/theme-' + savedTheme + '.css';
        document.head.appendChild(link);
    }

    // ── 1. Highlight active navigation link ──────────────
    const path = window.location.pathname;
    const links = document.querySelectorAll('.nav-link, .dropdown-link');
    links.forEach(link => {
        if (link.getAttribute('href') === path) {
            link.classList.add('active');
            if (link.classList.contains('dropdown-link')) {
                const parentNav = link.closest('.nav-item.dropdown').querySelector('.nav-link');
                if (parentNav) parentNav.classList.add('active');
            }
        }
    });

    // ── 2. Mobile menu toggle ────────────────────────────
    const toggleBtn = document.querySelector('.mobile-toggle');
    const navLinks = document.querySelector('.nav-links');
    if (toggleBtn && navLinks) {
        toggleBtn.addEventListener('click', () => {
            navLinks.classList.toggle('active');
            toggleBtn.textContent = navLinks.classList.contains('active') ? '✕' : '☰';
        });
    }

    // ── 3. Global sidebar TOC + collapsible references ───
    const wikiPage = document.querySelector('.wiki-page');
    const wikiMain = document.getElementById('wikiMain');
    const sidebarList = document.getElementById('wikiSidebarList');
    if (!wikiPage || !wikiMain || !sidebarList) return;

    // If the page opts out, hide sidebar immediately
    if (wikiMain.querySelector('.no-wiki-sidebar')) {
        wikiPage.classList.add('wiki-page--no-sidebar');
        return;
    }

    // --- 3a. Collapse a "References" section into a dropdown ---
    (function collapseReferences() {
        // Look for headings inside any .glass-card or .md-content
        const cards = wikiMain.querySelectorAll('.glass-card, .md-content');
        cards.forEach(card => {
            const hh = card.querySelectorAll('h2, h3');
            let refH = null;
            for (let i = 0; i < hh.length; i++) {
                if (/^\s*references\s*:?\s*$/i.test(hh[i].textContent)) {
                    refH = hh[i]; break;
                }
            }
            if (!refH) return;

            // Gather every sibling after the heading
            const after = [];
            let n = refH.nextSibling;
            while (n) { after.push(n); n = n.nextSibling; }

            const det = document.createElement('details');
            det.className = 'wiki-ref-dropdown';
            det.id = 'section-references';

            const sum = document.createElement('summary');
            sum.textContent = refH.textContent.replace(/[:\s]+$/, '');
            det.appendChild(sum);

            const body = document.createElement('div');
            body.className = 'wiki-ref-body';
            after.forEach(s => body.appendChild(s));
            det.appendChild(body);

            refH.parentNode.replaceChild(det, refH);
        });
    })();

    // --- 3a½. Process ((info: key)) inline dropdowns -----
    // Pages register content via: window.DROPDOWN_CONTENT = { key: { title, body } }
    // This runs before the TOC build so dropdown elements aren't indexed.
    (function processInfoDropdowns() {
        const contentMap = window.DROPDOWN_CONTENT;
        if (!contentMap || Object.keys(contentMap).length === 0) return;

        // Marker pattern: ((info: some label))
        const pattern = /\(\(info:\s*(.+?)\)\)/gi;

        // Collect all matching text nodes first (avoid mutating DOM during walk)
        const walker = document.createTreeWalker(wikiMain, NodeFilter.SHOW_TEXT, null, false);
        const matched = [];
        let n;
        while (n = walker.nextNode()) {
            if (pattern.test(n.nodeValue)) matched.push(n);
            pattern.lastIndex = 0;
        }

        matched.forEach(textNode => {
            const parent = textNode.parentNode;
            const text = textNode.nodeValue;
            const frag = document.createDocumentFragment();
            let last = 0, m;

            pattern.lastIndex = 0;
            while ((m = pattern.exec(text)) !== null) {
                // Text before match
                if (m.index > last) {
                    frag.appendChild(document.createTextNode(text.slice(last, m.index)));
                }

                const label = m[1].trim().replace(/\\/g, '');
                const key = label.toLowerCase();
                const entry = contentMap[key];

                // Trigger pill
                const trig = document.createElement('span');
                trig.className = 'info-trigger';
                trig.setAttribute('role', 'button');
                trig.setAttribute('tabindex', '0');
                trig.setAttribute('aria-expanded', 'false');
                trig.innerHTML = `${label} <span class="info-chevron">▼</span>`;

                // Expandable bar
                const bar = document.createElement('div');
                bar.className = 'info-bar';
                if (entry) {
                    bar.innerHTML = `<div class="info-bar__inner">
                        <div class="info-bar__title">${entry.title}</div>
                        <div class="info-bar__text">${entry.body}</div>
                    </div>`;
                } else {
                    bar.innerHTML = `<div class="info-bar__inner">
                        <div class="info-bar__title">${label}</div>
                        <div class="info-bar__text"><p>Content coming soon.</p></div>
                    </div>`;
                }

                // Toggle logic
                const toggle = () => {
                    const open = bar.classList.toggle('open');
                    trig.classList.toggle('active');
                    trig.setAttribute('aria-expanded', String(open));
                };
                trig.addEventListener('click', toggle);
                trig.addEventListener('keydown', e => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
                });

                trig._bar = bar;
                frag.appendChild(trig);
                last = m.index + m[0].length;
            }

            // Remaining text
            if (last < text.length) {
                frag.appendChild(document.createTextNode(text.slice(last)));
            }

            parent.replaceChild(frag, textNode);

            // Place each bar after the containing paragraph
            parent.querySelectorAll('.info-trigger').forEach(t => {
                if (t._bar) {
                    const target = parent.closest('p') || parent;
                    target.parentNode.insertBefore(t._bar, target.nextSibling);
                    delete t._bar;
                }
            });
        });
    })();

    // --- 3b. Build the sidebar TOC from h2/h3 headings ---
    const headings = wikiMain.querySelectorAll('h2, h3');
    const entries = [];
    const usedSlugs = {};

    headings.forEach(h => {
        // Skip headings inside the collapsed references dropdown
        if (h.closest('.wiki-ref-dropdown')) return;

        // Skip headings with empty or whitespace-only text
        if (!h.textContent.trim()) return;

        // Generate a unique slug for the heading
        let slug = h.textContent.trim()
            .toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .replace(/\s+/g, '-');
        if (usedSlugs[slug]) { slug += '-' + (++usedSlugs[slug]); }
        else { usedSlugs[slug] = 1; }
        if (!h.id) h.id = slug;

        const li = document.createElement('li');
        const a = document.createElement('a');
        a.className = 'wiki-sidebar__link'
            + (h.tagName === 'H3' ? ' wiki-sidebar__link--sub' : '');
        a.href = '#' + h.id;
        a.textContent = h.textContent.trim();
        a.addEventListener('click', e => {
            e.preventDefault();

            // If the heading is inside a hidden case-study panel, reveal it first
            const studyPanel = h.closest('.study-content');
            if (studyPanel && studyPanel.style.display === 'none') {
                // Hide all study panels and deactivate all carousel buttons
                document.querySelectorAll('.study-content').forEach(s => s.style.display = 'none');
                document.querySelectorAll('.carousel-btn').forEach(b => b.classList.remove('active'));

                // Show this panel
                studyPanel.style.display = 'block';

                // Activate the matching carousel button
                const panels = Array.from(document.querySelectorAll('.study-content'));
                const idx = panels.indexOf(studyPanel);
                const btns = document.querySelectorAll('.carousel-btn');
                if (btns[idx]) btns[idx].classList.add('active');
            }

            h.scrollIntoView({ behavior: 'smooth' });
        });
        li.appendChild(a);
        sidebarList.appendChild(li);
        entries.push({ el: h, link: a });
    });

    // Add the References dropdown as the last TOC entry if it exists
    const refDet = wikiMain.querySelector('.wiki-ref-dropdown');
    if (refDet) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.className = 'wiki-sidebar__link';
        a.href = '#' + refDet.id;
        a.textContent = 'References';
        a.addEventListener('click', e => {
            e.preventDefault();
            refDet.open = true;
            refDet.scrollIntoView({ behavior: 'smooth' });
        });
        li.appendChild(a);
        sidebarList.appendChild(li);
        entries.push({ el: refDet, link: a });
    }

    // If no entries, hide sidebar and go full-width
    if (entries.length === 0) {
        wikiPage.classList.add('wiki-page--no-sidebar');
        return;
    }

    // --- 3c. Scroll-spy: highlight active heading --------
    let active = entries[0].link;
    active.classList.add('wiki-sidebar__link--active');

    const observer = new IntersectionObserver(records => {
        records.forEach(r => {
            if (!r.isIntersecting) return;
            const match = entries.find(e => e.el === r.target);
            if (!match) return;
            if (active) active.classList.remove('wiki-sidebar__link--active');
            match.link.classList.add('wiki-sidebar__link--active');
            active = match.link;
        });
    }, {
        rootMargin: '-80px 0px -60% 0px',
        threshold: 0
    });

    entries.forEach(e => observer.observe(e.el));
});
