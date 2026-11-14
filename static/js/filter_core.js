// static/js/filter_core.js
// Общий код для мультиселектов фильтров и сохранения состояния в cookie.
// Используется на hourly_table.html и sankey.html.

const FilterCore = (function () {
    let appliedFilterSignature = '';
    let _listenersInstalled = false;

    // ---------- сбор значений ----------
    function collectFilter() {
        const filters = {};
        document.querySelectorAll('select[data-filter-key]').forEach(sel => {
            const key = sel.dataset.filterKey;
            if (!key) return;
            const values = Array.from(sel.selectedOptions)
                .map(o => o.value)
                .filter(Boolean);
            if (values.length) filters[key] = values;
        });
        return filters;
    }

    function restoreFiltersFromInitial(initialFilters) {
        const initial = initialFilters || {};
        document.querySelectorAll('select[data-filter-key]').forEach(sel => {
            const key = sel.dataset.filterKey;
            const wanted = new Set(initial[key] || []);
            Array.from(sel.options).forEach(o => {
                o.selected = wanted.has(o.value);
            });
        });
    }

    function filterSignature() {
        return JSON.stringify(collectFilter());
    }

    function getAppliedSignature() {
        return appliedFilterSignature;
    }

    function setAppliedSignature(sig) {
        appliedFilterSignature = sig !== undefined ? sig : filterSignature();
    }

    function hasPendingChanges() {
        return filterSignature() !== appliedFilterSignature;
    }

    // ---------- бейджи и подсветка ----------
    function updateFilterBadges() {
        document.querySelectorAll('select[data-filter-key]').forEach(sel => {
            const badge = document.querySelector(`[data-count-for="${sel.id}"]`);
            if (badge) badge.textContent = sel.selectedOptions.length;
        });

        const pending = hasPendingChanges();
        document.querySelectorAll('select[data-filter-key]').forEach(sel => {
            sel.classList.toggle('filter-pending', pending);
        });
        document.querySelectorAll('[data-count-for]').forEach(el => {
            el.classList.toggle('filter-pending-badge', pending);
        });
        const applyBtn = document.getElementById('applyFiltersBtn');
        if (applyBtn) {
            applyBtn.classList.toggle('btn-warning', pending);
            applyBtn.classList.toggle('btn-primary', !pending);
        }
    }

    // ---------- настройка мультиселектов ----------
    function setupFilterListeners(onApply) {
        const selects = Array.from(document.querySelectorAll('select[data-filter-key]'));
        const applyBtn = document.getElementById('applyFiltersBtn');

        const filterZoneEls = [];
        selects.forEach(sel => {
            const wrap = sel.closest('.filter-select-wrap');
            const lbl = document.querySelector(`label[for="${sel.id}"]`);
            filterZoneEls.push(sel, wrap, lbl);
        });
        filterZoneEls.push(applyBtn);

        function openSelect(sel) {
            if (sel._closedSize === undefined) sel._closedSize = sel.size;
            sel.size = Math.min(Math.max(sel.options.length, 2), 10);
            const wrap = sel.closest('.filter-select-wrap');
            if (wrap) wrap.classList.add('is-open');
        }
        function closeSelect(sel) {
            sel.size = (sel._closedSize !== undefined) ? sel._closedSize : 1;
            const wrap = sel.closest('.filter-select-wrap');
            if (wrap) wrap.classList.remove('is-open');
        }

        selects.forEach(sel => {
            sel.addEventListener('mousedown', function (e) {
                if (e.target.tagName === 'OPTION' && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
                    e.preventDefault();
                    e.target.selected = !e.target.selected;
                    updateFilterBadges();
                }
                openSelect(sel);
            });
            sel.addEventListener('focus', () => openSelect(sel));
            sel.addEventListener('change', () => updateFilterBadges());
            sel.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    closeSelect(sel);
                    if (typeof onApply === 'function') onApply();
                }
            });
            sel.addEventListener('blur', function () {
                setTimeout(() => closeSelect(sel), 150);
            });
        });

        if (!_listenersInstalled) {
            _listenersInstalled = true;
            document.addEventListener('mousedown', function (e) {
                const inside = filterZoneEls.some(el => el && (el === e.target || el.contains(e.target)));
                if (inside) return;

                document.querySelectorAll('select[data-filter-key]').forEach(sel => {
                    if (sel.size > 1) {
                        sel.size = (sel._closedSize !== undefined) ? sel._closedSize : 1;
                        const wrap = sel.closest('.filter-select-wrap');
                        if (wrap) wrap.classList.remove('is-open');
                    }
                });
                if (hasPendingChanges() && typeof onApply === 'function') onApply();
            });
        }

        updateFilterBadges();
    }

    // ---------- сохранение cookie ----------
    function persistFiltersToCookie(endpoint, extra) {
        const body = Object.assign({
            filters: collectFilter(),
            date: (document.getElementById('analysisDate') || {}).value,
            zone_type: (extra && extra.zone_type) || '',
        }, extra || {});
        delete body.zone_type === '' ? body.zone_type : '';

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            keepalive: true,
        }).catch(err => console.warn('Не удалось сохранить фильтры:', err));
    }

    return {
        collectFilter,
        restoreFiltersFromInitial,
        filterSignature,
        getAppliedSignature,
        setAppliedSignature,
        hasPendingChanges,
        updateFilterBadges,
        setupFilterListeners,
        persistFiltersToCookie,
    };
})();