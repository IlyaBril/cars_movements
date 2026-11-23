/* ============================================================
 *  Sankey диаграмма — логика страницы
 * ============================================================ */

(function () {
    'use strict';

    // ============================================================
    //  КОНФИГ (из window.SANKEY_CONFIG)
    // ============================================================
    const CFG = window.SANKEY_CONFIG || {};
    const INITIAL_STATE = {
        zoneType: CFG.zoneType,
        filters: CFG.filters,
        autoRefresh: CFG.autoRefresh,
    };
    const DEFAULT_DATE = CFG.defaultDate || '';
    const FIRST_ZONE_TYPE = CFG.firstZoneType || 'main';

    // ============================================================
    //  ГЛОБАЛЬНОЕ СОСТОЯНИЕ
    // ============================================================
    let currentZoneType = INITIAL_STATE.zoneType || FIRST_ZONE_TYPE;
    let refreshTimer = null;
    let isAutoRefreshEnabled = INITIAL_STATE.autoRefresh !== false;
    let showCoords = false;
    let lastNodePositions = {};

    let pendingColors = {};   // { label: { color, opacity } }
    let serverColors = {};    // { label: { color, opacity } }

    let colorPickerOpenFor = null;
    let graphDivInstance = null;

    // ============================================================
    //  УТИЛИТЫ ЦВЕТА
    // ============================================================
    function hexToRgba(hex, opacity) {
        if (!hex) return `rgba(136,136,136,${opacity})`;
        if (typeof hex === 'string' && hex.startsWith('rgba')) return hex;

        let h = String(hex).replace('#', '').trim();
        if (h.length === 3) h = h.split('').map(c => c + c).join('');
        if (h.length !== 6) return `rgba(136,136,136,${opacity})`;

        const r = parseInt(h.substring(0, 2), 16);
        const g = parseInt(h.substring(2, 4), 16);
        const b = parseInt(h.substring(4, 6), 16);
        const a = (opacity === undefined || opacity === null) ? 1 : opacity;
        return `rgba(${r},${g},${b},${a})`;
    }

    function normalizeStyle(entry, fallbackColor) {
        if (!entry) return { color: fallbackColor || '#888888', opacity: 1 };
        if (typeof entry === 'string') return { color: entry, opacity: 1 };
        return {
            color: entry.color || fallbackColor || '#888888',
            opacity: (entry.opacity === undefined || entry.opacity === null) ? 1 : entry.opacity
        };
    }

    // ============================================================
    //  ФИЛЬТРЫ
    // ============================================================
    function applyFiltersNow() {
        FilterCore.setAppliedSignature();
        FilterCore.updateFilterBadges();
        FilterCore.persistFiltersToCookie('/sankey-filters', { zone_type: currentZoneType });
        loadSankeyData(true);
    }

    function resetFilters() {
        document.querySelectorAll('select[data-filter-key]').forEach(sel => {
            sel.selectedIndex = -1;
        });
        FilterCore.setAppliedSignature();
        FilterCore.updateFilterBadges();
        FilterCore.persistFiltersToCookie('/sankey-filters', { zone_type: currentZoneType });
        loadSankeyData(true);
    }

    // ============================================================
    //  ПЕРЕКЛЮЧЕНИЕ ЗОНЫ
    // ============================================================
    function switchZoneType(type) {
        currentZoneType = type;
        const label = document.getElementById('selectedZone');
        if (label) label.textContent = type;

        pendingColors = {};
        serverColors = {};
        colorPickerOpenFor = null;

        FilterCore.setAppliedSignature();
        FilterCore.persistFiltersToCookie('/sankey-filters', { zone_type: type });
        loadSankeyData(true);
    }

    // ============================================================
    //  АВТООБНОВЛЕНИЕ
    // ============================================================
    function toggleAutoRefresh() {
        isAutoRefreshEnabled = document.getElementById('autoRefreshSwitch').checked;
        FilterCore.persistFiltersToCookie('/sankey-filters', { zone_type: currentZoneType });
        if (isAutoRefreshEnabled) {
            startAutoRefresh();
            showMessage('Автообновление включено', 'success');
        } else {
            stopAutoRefresh();
            showMessage('Автообновление выключено', 'info');
        }
    }

    function startAutoRefresh() {
        stopAutoRefresh();
        const intervalMs = parseInt(document.getElementById('refreshInterval').value) * 1000;
        refreshTimer = setInterval(() => {
            if (isAutoRefreshEnabled) loadSankeyData(false);
        }, intervalMs);
    }

    function stopAutoRefresh() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
    }

    function onRefreshIntervalChange() {
        if (isAutoRefreshEnabled) {
            startAutoRefresh();
            const minutes = parseInt(document.getElementById('refreshInterval').value) / 60;
            showMessage(`Интервал обновления изменен на ${minutes} мин`, 'info');
        }
    }

    function disableAutoRefresh(reason) {
        const sw = document.getElementById('autoRefreshSwitch');
        const wasChecked = sw && sw.checked;
        isAutoRefreshEnabled = false;
        if (sw) sw.checked = false;
        stopAutoRefresh();
        if (wasChecked) showMessage(`Автообновление отключено: ${reason}`, 'info');
    }

    // ============================================================
    //  ВСПОМОГАТЕЛЬНЫЕ
    // ============================================================
    function updateTitle(dateString) {
        const formattedDate = dateString ? formatDate(dateString) : DEFAULT_DATE;
        document.getElementById('topMessage').textContent =
            `Диаграмма потоков ${currentZoneType} ${formattedDate}`;
    }

    function formatDate(dateString) {
        if (!dateString) return DEFAULT_DATE;
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            year: 'numeric', month: '2-digit', day: '2-digit'
        });
    }

    function showMessage(msg, type) {
        const div = document.getElementById('uploadMessage');
        const alertClass = type === 'error' ? 'alert-danger' :
                          type === 'info' ? 'alert-info' : 'alert-success';
        div.innerHTML = `
            <div class="alert ${alertClass} alert-dismissible fade show small" role="alert">
                ${msg}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        setTimeout(() => { div.innerHTML = ''; }, 5000);
    }

    function showLoading() {
        document.getElementById('loadingIndicator').classList.remove('d-none');
        document.getElementById('loadingSpinner').style.display = 'block';
    }

    function hideLoading() {
        document.getElementById('loadingIndicator').classList.add('d-none');
        document.getElementById('loadingSpinner').style.display = 'none';
    }

    // ============================================================
    //  ПАНЕЛЬ КООРДИНАТ
    // ============================================================
    function toggleCoordinates() {
        showCoords = !showCoords;
        const display = document.getElementById('coordinatesDisplay');
        const btn = document.getElementById('toggleCoordsBtn');

        if (showCoords) {
            display.classList.add('show');
            btn.classList.add('show');
            setTimeout(updateCoordinates, 200);
        } else {
            display.classList.remove('show');
            btn.classList.add('show');
        }
    }

    function closeCoordinates() {
        showCoords = false;
        colorPickerOpenFor = null;
        document.getElementById('coordinatesDisplay').classList.remove('show');
        document.getElementById('toggleCoordsBtn').classList.add('show');
    }

    // ============================================================
    //  ЧТЕНИЕ ДАННЫХ ИЗ PLOTLY
    // ============================================================
    function getNodeCoordinates(graphDiv) {
        try {
            const sources = [graphDiv?.layout?.sankey?.node, graphDiv?.data?.[0]?.node];
            for (const source of sources) {
                if (source?.x && source?.y) {
                    const labels = source.label || [];
                    return labels.map((label, i) => ({
                        label: label || `Node ${i}`,
                        x: source.x[i],
                        y: source.y[i],
                        index: i
                    }));
                }
            }
            return [];
        } catch (e) {
            console.warn('Ошибка получения координат:', e);
            return [];
        }
    }

    function getNodeColors(graphDiv) {
        try {
            const sources = [graphDiv?.layout?.sankey?.node, graphDiv?.data?.[0]?.node];
            for (const src of sources) {
                if (src?.color) {
                    if (typeof src.color === 'string') return [];
                    return src.color;
                }
            }
        } catch (e) { /* ignore */ }
        return [];
    }

    function getLinkColors(graphDiv) {
        try {
            const src = graphDiv?.data?.[0];
            const c = src?.link?.color;
            if (!c) return null;
            if (typeof c === 'string') return null;
            return c.slice();
        } catch (e) { return null; }
    }

    function getLinkSourceArray(graphDiv) {
        try {
            const src = graphDiv?.data?.[0];
            const s = src?.link?.source;
            if (!s) return [];
            return Array.from(s);
        } catch (e) { return []; }
    }

    function readServerColorsFromGraph() {
        const graphDiv = document.querySelector('.plotly-graph-div');
        const result = {};
        if (!graphDiv) return result;
        try {
            const positions = getNodeCoordinates(graphDiv);
            const colors = getNodeColors(graphDiv);
            positions.forEach((p, i) => {
                const raw = colors[i];
                if (!raw) return;
                if (typeof raw === 'string' && raw.startsWith('rgba')) {
                    const m = raw.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\)/);
                    if (m) {
                        const r = parseInt(m[1]).toString(16).padStart(2, '0');
                        const g = parseInt(m[2]).toString(16).padStart(2, '0');
                        const b = parseInt(m[3]).toString(16).padStart(2, '0');
                        const a = (m[4] !== undefined) ? parseFloat(m[4]) : 1;
                        result[p.label] = { color: `#${r}${g}${b}`, opacity: a };
                        return;
                    }
                }
                result[p.label] = { color: raw, opacity: 1 };
            });
        } catch (e) { /* ignore */ }
        return result;
    }

    // ============================================================
    //  РЕНДЕР ПАНЕЛИ КООРДИНАТ
    // ============================================================
    function updateCoordinates() {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv || typeof Plotly === 'undefined') {
            document.getElementById('coordinatesList').innerHTML =
                '<div class="text-muted small">График не загружен</div>';
            return;
        }

        try {
            const positions = getNodeCoordinates(graphDiv);
            const nodeColors = getNodeColors(graphDiv);

            if (positions.length === 0) {
                document.getElementById('coordinatesList').innerHTML =
                    '<div class="text-muted small">Нет данных об узлах. Перетащите узел.</div>';
                document.getElementById('coordStatus').textContent = 'Ожидание данных...';
                return;
            }

            let html = '';
            let hasChanges = false;
            let changedNodes = [];

            positions.forEach(p => {
                const key = `${p.label}_${p.index}`;
                const roundedX = Math.round(p.x * 100) / 100;
                const roundedY = Math.round(p.y * 100) / 100;

                const styleFromPending = pendingColors[p.label];
                const styleFromServer = serverColors[p.label];
                const fallbackColor = nodeColors[p.index] || '#888888';

                let currentColor, currentOpacity;
                if (styleFromPending) {
                    const st = normalizeStyle(styleFromPending, fallbackColor);
                    currentColor = st.color;
                    currentOpacity = st.opacity;
                } else if (styleFromServer) {
                    const st = normalizeStyle(styleFromServer, fallbackColor);
                    currentColor = st.color;
                    currentOpacity = st.opacity;
                } else {
                    const raw = nodeColors[p.index];
                    if (typeof raw === 'string' && raw.startsWith('rgba')) {
                        const m = raw.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\)/);
                        if (m) {
                            const r = parseInt(m[1]).toString(16).padStart(2, '0');
                            const g = parseInt(m[2]).toString(16).padStart(2, '0');
                            const b = parseInt(m[3]).toString(16).padStart(2, '0');
                            currentColor = `#${r}${g}${b}`;
                            currentOpacity = (m[4] !== undefined) ? parseFloat(m[4]) : 1;
                        } else {
                            currentColor = raw || '#888888';
                            currentOpacity = 1;
                        }
                    } else {
                        currentColor = raw || '#888888';
                        currentOpacity = 1;
                    }
                }

                let isChanged = false;
                if (lastNodePositions[key]) {
                    const lastX = Math.round(lastNodePositions[key].x * 100) / 100;
                    const lastY = Math.round(lastNodePositions[key].y * 100) / 100;
                    if (lastX !== roundedX || lastY !== roundedY) {
                        hasChanges = true;
                        isChanged = true;
                        changedNodes.push(p.label);
                    }
                }
                lastNodePositions[key] = { x: p.x, y: p.y };

                const pickerOpen = colorPickerOpenFor === p.label;
                const opacityPercent = Math.round(currentOpacity * 100);

                const pickerHtml = pickerOpen
                    ? `<div class="color-picker-panel">
                           <div class="color-picker-row">
                               <input type="color" value="${currentColor}"
                                      oninput="Sankey.onColorInput(${p.index}, this.value)"
                                      onchange="Sankey.onColorChange(${p.index}, this.value)">
                               <span class="opacity-preview" data-preview-index="${p.index}"
                                     style="background-color: ${hexToRgba(currentColor, currentOpacity)};"></span>
                               <span class="picker-hint">цвет не закроет панель</span>
                               <button class="close-btn" style="font-size:14px; margin-left:4px;"
                                       onclick="Sankey.closeColorPicker()" title="Закрыть панель">✕</button>
                           </div>
                           <div class="opacity-row">
                               <label>Прозрачность</label>
                               <input type="range" min="0" max="100" step="1"
                                      value="${opacityPercent}"
                                      data-opacity-index="${p.index}"
                                      oninput="Sankey.onOpacityInput(${p.index}, this.value)"
                                      onchange="Sankey.onOpacityChange(${p.index}, this.value)">
                               <span class="opacity-value" data-opacity-val="${p.index}">${opacityPercent}%</span>
                           </div>
                       </div>`
                    : '';

                const safeLabel = String(p.label)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;');

                html += `
                    <div class="coord-item">
                        <div class="coord-row">
                            <span class="coord-label" data-node-index="${p.index}"
                                  title="Кликните для настройки цвета и прозрачности"
                                  onclick="Sankey.openColorPickerByIndex(${p.index})">
                                <span class="coord-color-dot" data-dot-index="${p.index}"
                                      style="background:${hexToRgba(currentColor, currentOpacity)};"></span>
                                ${safeLabel}
                            </span>
                            <span class="coord-value ${isChanged ? 'coord-changed' : ''}">
                                (${roundedX.toFixed(2)}, ${roundedY.toFixed(2)}) · ${opacityPercent}%${isChanged ? ' ✦' : ''}
                            </span>
                        </div>
                        ${pickerHtml}
                    </div>
                `;
            });

            document.getElementById('coordinatesList').innerHTML = html;

            if (hasChanges && changedNodes.length > 0) {
                document.getElementById('coordStatus').textContent =
                    `🔄 Перемещены: ${changedNodes.join(', ')}`;
                document.getElementById('coordStatus').style.color = '#ffd54f';
            } else {
                const changedColors = Object.keys(pendingColors).length;
                document.getElementById('coordStatus').textContent =
                    changedColors > 0
                        ? `🎨 Изменено узлов: ${changedColors}. Не забудьте сохранить`
                        : `✓ ${positions.length} узлов. Клик по имени — цвет и прозрачность`;
                document.getElementById('coordStatus').style.color =
                    changedColors > 0 ? '#ffd54f' : '#aaa';
            }
        } catch (e) {
            console.warn('Ошибка при обновлении координат:', e);
            document.getElementById('coordinatesList').innerHTML =
                '<div class="text-danger small">Ошибка получения координат</div>';
        }
    }

    // ============================================================
    //  РАБОТА С ЦВЕТОМ И ПРОЗРАЧНОСТЬЮ
    // ============================================================
    function openColorPickerByIndex(index) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv) return;
        const positions = getNodeCoordinates(graphDiv);
        const node = positions.find(p => p.index === index);
        if (!node) return;
        colorPickerOpenFor = node.label;
        updateCoordinates();
    }

    function closeColorPicker() {
        colorPickerOpenFor = null;
        updateCoordinates();
    }

    function onColorInput(index, color) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv) return;
        const positions = getNodeCoordinates(graphDiv);
        const node = positions.find(p => p.index === index);
        if (!node) return;

        const curOpacity = getCurrentOpacityForLabel(node.label);
        applyNodeAppearanceByIndex(index, color, curOpacity);
        updateInlinePreview(index, color, curOpacity);
    }

    function onColorChange(index, color) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv) return;
        const positions = getNodeCoordinates(graphDiv);
        const node = positions.find(p => p.index === index);
        if (!node) return;

        const curOpacity = getCurrentOpacityForLabel(node.label);
        pendingColors[node.label] = { color: color, opacity: curOpacity };

        applyNodeAppearanceByIndex(index, color, curOpacity);
        disableAutoRefresh('изменён цвет узла');
        updateCoordinates();
    }

    function onOpacityInput(index, value) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv) return;
        const positions = getNodeCoordinates(graphDiv);
        const node = positions.find(p => p.index === index);
        if (!node) return;

        const opacity = clamp01(parseInt(value, 10) / 100);
        const curColor = getCurrentColorForLabel(node.label);

        const valEl = document.querySelector(`[data-opacity-val="${index}"]`);
        if (valEl) valEl.textContent = Math.round(opacity * 100) + '%';

        applyNodeAppearanceByIndex(index, curColor, opacity);
        updateInlinePreview(index, curColor, opacity);
    }

    function onOpacityChange(index, value) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv) return;
        const positions = getNodeCoordinates(graphDiv);
        const node = positions.find(p => p.index === index);
        if (!node) return;

        const opacity = clamp01(parseInt(value, 10) / 100);
        const curColor = getCurrentColorForLabel(node.label);

        pendingColors[node.label] = { color: curColor, opacity: opacity };

        applyNodeAppearanceByIndex(index, curColor, opacity);
        disableAutoRefresh('изменена прозрачность узла');
        updateCoordinates();
    }

    function clamp01(v) {
        if (isNaN(v)) return 1;
        return Math.max(0, Math.min(1, v));
    }

    function getCurrentOpacityForLabel(label) {
        if (pendingColors[label]) return normalizeStyle(pendingColors[label]).opacity;
        if (serverColors[label]) return normalizeStyle(serverColors[label]).opacity;
        return 1;
    }

    function getCurrentColorForLabel(label) {
        if (pendingColors[label]) return normalizeStyle(pendingColors[label]).color;
        if (serverColors[label]) return normalizeStyle(serverColors[label]).color;
        return '#888888';
    }

    function updateInlinePreview(index, color, opacity) {
        const preview = document.querySelector(`[data-preview-index="${index}"]`);
        if (preview) preview.style.backgroundColor = hexToRgba(color, opacity);

        const dot = document.querySelector(`.coord-color-dot[data-dot-index="${index}"]`);
        if (dot) dot.style.background = hexToRgba(color, opacity);
    }

    // ============================================================
    //  ПРИМЕНЕНИЕ ВНЕШНЕГО ВИДА УЗЛА
    // ============================================================
    function applyNodeAppearanceByIndex(index, color, opacity) {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv || typeof Plotly === 'undefined') return;

        try {
            const positions = getNodeCoordinates(graphDiv);
            const nodeCount = positions.length;
            const rgba = hexToRgba(color, opacity);

            const nodeColors = getNodeColors(graphDiv).slice();
            while (nodeColors.length < nodeCount) nodeColors.push('#888888');
            nodeColors[index] = rgba;

            const sources = getLinkSourceArray(graphDiv);
            let linkColors = getLinkColors(graphDiv);

            if (linkColors && linkColors.length === sources.length) {
                linkColors = linkColors.slice();
                for (let i = 0; i < sources.length; i++) {
                    if (sources[i] === index) linkColors[i] = rgba;
                }
            } else {
                linkColors = sources.map(srcIdx => {
                    if (srcIdx === index) return rgba;
                    return (nodeColors[srcIdx] || '#cccccc');
                });
            }

            Plotly.restyle(graphDiv, {
                'node.color': [nodeColors],
                'link.color': [linkColors]
            }, [0]);
        } catch (e) {
            console.warn('Не удалось применить цвет/прозрачность:', e);
        }
    }

    // ============================================================
    //  PLOTLY ОБРАБОТЧИКИ
    // ============================================================
    function setupNodeDragHandler(graphDiv) {
        if (!graphDiv) return;
        graphDivInstance = graphDiv;

        const handlers = ['_sankeyDragHandler', '_sankeyAfterPlotHandler', '_sankeyHoverHandler'];
        handlers.forEach(name => {
            if (graphDiv[name]) {
                graphDiv.removeListener(
                    name === '_sankeyDragHandler' ? 'plotly_relayout' :
                    name === '_sankeyAfterPlotHandler' ? 'plotly_afterplot' : 'plotly_hover',
                    graphDiv[name]
                );
            }
        });

        graphDiv._sankeyDragHandler = function(eventData) {
            if (eventData && eventData['sankey.node.x'] !== undefined) {
                disableAutoRefresh('перемещён узел');
                setTimeout(() => { if (showCoords) updateCoordinates(); }, 100);
            }
        };
        graphDiv.on('plotly_relayout', graphDiv._sankeyDragHandler);

        graphDiv._sankeyAfterPlotHandler = function() {
            if (showCoords && !colorPickerOpenFor) setTimeout(updateCoordinates, 150);
        };
        graphDiv.on('plotly_afterplot', graphDiv._sankeyAfterPlotHandler);

        graphDiv._sankeyHoverHandler = function() {
            if (showCoords && !colorPickerOpenFor) setTimeout(updateCoordinates, 50);
        };
        graphDiv.on('plotly_hover', graphDiv._sankeyHoverHandler);
    }

    // ============================================================
    //  СБОРКА URL С ФИЛЬТРОМ
    // ============================================================
    function buildQueryParams(extra = {}) {
        const params = new URLSearchParams();

        const date = document.getElementById('analysisDate').value;
        if (date) params.set('date', date);
        params.set('zone_type', currentZoneType);

        const filters = FilterCore.collectFilter();
        if (Object.keys(filters).length) {
            params.set('filter', JSON.stringify(filters));
        }

        Object.entries(extra).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== '') params.set(k, v);
        });

        return params.toString();
    }

    // ============================================================
    //  ЗАГРУЗКА ДАННЫХ
    // ============================================================
    function loadSankeyData(showIndicator = true) {
        const date = document.getElementById('analysisDate').value;

        updateTitle(date);
        if (showIndicator) showLoading();

        $('#chartContainer').css('visibility', 'hidden');

        const url = '/sankey-chart?' + buildQueryParams();

        $.ajax({
            url: url,
            method: 'GET',
            success: function(data) {
                $('#chartContent').html(data);
                if (showIndicator) hideLoading();

                lastNodePositions = {};
                pendingColors = {};
                colorPickerOpenFor = null;

                requestAnimationFrame(function() {
                    setTimeout(function() {
                        const graphDiv = document.querySelector('.plotly-graph-div');
                        if (graphDiv && typeof Plotly !== 'undefined') {
                            Plotly.relayout(graphDiv, { autosize: true, height: undefined });
                            Plotly.Plots.resize(graphDiv);
                            setupNodeDragHandler(graphDiv);

                            serverColors = readServerColorsFromGraph();

                            setTimeout(() => {
                                if (showCoords) updateCoordinates();
                                requestAnimationFrame(() => {
                                    $('#chartContainer').css('visibility', 'visible');
                                });
                            }, 300);
                        } else {
                            $('#chartContainer').css('visibility', 'visible');
                        }
                    }, 100);
                });
            },
            error: function(xhr) {
                if (showIndicator) hideLoading();
                $('#chartContent').html(`
                    <div class="alert alert-danger">
                        Ошибка загрузки диаграммы: ${xhr.responseText || 'Неизвестная ошибка'}
                    </div>
                `);
                $('#chartContainer').css('visibility', 'visible');
                showMessage('Ошибка загрузки диаграммы', 'error');
            }
        });
    }

    // ============================================================
    //  GIF
    // ============================================================
    function downloadGif() {
        const interval = document.getElementById('gifInterval').value;
        const duration = document.getElementById('gifDuration').value;

        const url = '/sankey-gif?' + buildQueryParams({
            interval_minutes: interval,
            duration: duration,
            max_frames: 24,
        });

        showMessage('Генерация GIF началась. Файл будет скачан автоматически', 'success');
        window.open(url, '_blank');
    }

    // ============================================================
    //  СОХРАНЕНИЕ ПОЗИЦИЙ, ЦВЕТОВ И ПРОЗРАЧНОСТИ
    // ============================================================
    function saveNodePositions() {
        const graphDiv = document.querySelector('.plotly-graph-div');
        if (!graphDiv || typeof Plotly === 'undefined') {
            showMessage('График не загружен', 'error');
            return;
        }

        try {
            const positions = getNodeCoordinates(graphDiv);
            if (positions.length === 0) {
                showMessage('Нет данных об узлах для сохранения', 'error');
                return;
            }

            const actualColors = getNodeColors(graphDiv);
            const positionData = {};

            positions.forEach((p, i) => {
                let color, opacity;
                if (pendingColors[p.label]) {
                    const st = normalizeStyle(pendingColors[p.label]);
                    color = st.color;
                    opacity = st.opacity;
                } else if (serverColors[p.label]) {
                    const st = normalizeStyle(serverColors[p.label]);
                    color = st.color;
                    opacity = st.opacity;
                } else {
                    const raw = actualColors[i] || '#888888';
                    if (typeof raw === 'string' && raw.startsWith('rgba')) {
                        const m = raw.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\)/);
                        if (m) {
                            const r = parseInt(m[1]).toString(16).padStart(2, '0');
                            const g = parseInt(m[2]).toString(16).padStart(2, '0');
                            const b = parseInt(m[3]).toString(16).padStart(2, '0');
                            color = `#${r}${g}${b}`;
                            opacity = (m[4] !== undefined) ? parseFloat(m[4]) : 1;
                        } else {
                            color = raw;
                            opacity = 1;
                        }
                    } else {
                        color = raw;
                        opacity = 1;
                    }
                }

                positionData[p.label] = {
                    x: Math.round(p.x * 100) / 100,
                    y: Math.round(p.y * 100) / 100,
                    color: color,
                    opacity: opacity
                };
            });

            const zoneType = currentZoneType;
            $.ajax({
                url: `/sankey-save-positions?zone_type=${encodeURIComponent(zoneType)}`,
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(positionData),
                success: function(response) {
                    if (response.success) {
                        serverColors = Object.assign({}, serverColors, pendingColors);
                        pendingColors = {};
                        showMessage(`✅ Позиции, цвета и прозрачность для '${zoneType}' сохранены!`, 'success');
                        if (showCoords) updateCoordinates();
                    } else {
                        showMessage('❌ Ошибка сохранения: ' + (response.error || 'Неизвестная ошибка'), 'error');
                    }
                },
                error: function(xhr) {
                    showMessage('❌ Ошибка при сохранении: ' + xhr.responseText, 'error');
                }
            });
        } catch (e) {
            console.error('Ошибка сохранения позиций:', e);
            showMessage('❌ Ошибка: ' + e.message, 'error');
        }
    }

    // ============================================================
    //  ИНИЦИАЛИЗАЦИЯ
    // ============================================================
    $(document).ready(function() {
        FilterCore.restoreFiltersFromInitial(INITIAL_STATE.filters);
        FilterCore.setAppliedSignature();
        FilterCore.setupFilterListeners(applyFiltersNow);

        const autoSw = document.getElementById('autoRefreshSwitch');
        autoSw.checked = isAutoRefreshEnabled;
        autoSw.addEventListener('change', toggleAutoRefresh);

        document.getElementById('refreshInterval').addEventListener('change', onRefreshIntervalChange);

        document.getElementById('analysisDate').addEventListener('change', function() {
            FilterCore.persistFiltersToCookie('/sankey-filters', { zone_type: currentZoneType });
            loadSankeyData(true);
        });

        loadSankeyData(true);
        if (isAutoRefreshEnabled) startAutoRefresh();
        setTimeout(() => {
            document.getElementById('toggleCoordsBtn').classList.add('show');
        }, 1000);

        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (showCoords && !colorPickerOpenFor) updateCoordinates();
            }, 500);
        });
    });

    // ============================================================
    //  ОЧИСТКА
    // ============================================================
    window.addEventListener('beforeunload', function() {
        stopAutoRefresh();
        if (graphDivInstance) {
            ['_sankeyDragHandler', '_sankeyAfterPlotHandler', '_sankeyHoverHandler'].forEach(name => {
                if (graphDivInstance[name]) {
                    graphDivInstance.removeListener(
                        name === '_sankeyDragHandler' ? 'plotly_relayout' :
                        name === '_sankeyAfterPlotHandler' ? 'plotly_afterplot' : 'plotly_hover',
                        graphDivInstance[name]
                    );
                }
            });
        }
    });

    // ============================================================
    //  ЭКСПОРТ В ГЛОБАЛЬНУЮ ОБЛАСТЬ (для inline onclick в HTML)
    // ============================================================
    window.Sankey = {
        // обработчики из HTML
        switchZoneType: switchZoneType,
        applyFiltersNow: applyFiltersNow,
        resetFilters: resetFilters,
        downloadGif: downloadGif,
        saveNodePositions: saveNodePositions,
        toggleCoordinates: toggleCoordinates,
        closeCoordinates: closeCoordinates,

        // обработчики из динамического HTML панели координат
        openColorPickerByIndex: openColorPickerByIndex,
        closeColorPicker: closeColorPicker,
        onColorInput: onColorInput,
        onColorChange: onColorChange,
        onOpacityInput: onOpacityInput,
        onOpacityChange: onOpacityChange,
    };

    // Для обратной совместимости с inline `onclick="switchZoneType(...)"` в шаблоне:
    window.switchZoneType = switchZoneType;
    window.applyFiltersNow = applyFiltersNow;
    window.resetFilters = resetFilters;
    window.downloadGif = downloadGif;
    window.saveNodePositions = saveNodePositions;
    window.toggleCoordinates = toggleCoordinates;
    window.closeCoordinates = closeCoordinates;
    window.openColorPickerByIndex = openColorPickerByIndex;
    window.closeColorPicker = closeColorPicker;
    window.onColorInput = onColorInput;
    window.onColorChange = onColorChange;
    window.onOpacityInput = onOpacityInput;
    window.onOpacityChange = onOpacityChange;
})();