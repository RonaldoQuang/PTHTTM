/* app.js - hành vi giao diện dùng chung: thông báo tự đóng, nút "đang xử lý", ảnh lỗi, xem ảnh bằng chứng */
(function () {
    'use strict';

    /* ---------- 1. Thông báo tự đóng (lỗi thì giữ lại để người dùng đọc) ---------- */
    document.querySelectorAll('.alert').forEach(function (el) {
        if (el.classList.contains('alert-danger')) return;
        setTimeout(function () {
            el.classList.remove('show');
            setTimeout(function () { el.remove(); }, 300);
        }, 6000);
    });

    /* ---------- 2. Nút "đang xử lý" (chống bấm nhiều lần khi trang phải chờ lâu) ---------- */
    function setButtonLoading(btn) {
        if (!btn || btn.dataset.loadingActive) return;
        btn.dataset.loadingActive = '1';
        btn.dataset.originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' +
            (btn.dataset.loading || 'Đang xử lý...');
    }
    function resetButtons() {
        document.querySelectorAll('[data-loading-active]').forEach(function (b) {
            b.disabled = false;
            b.innerHTML = b.dataset.originalHtml;
            delete b.dataset.loadingActive;
        });
    }
    window.setButtonLoading = setButtonLoading;
    document.addEventListener('submit', function (e) {
        var btn = e.target.querySelector ? e.target.querySelector('[data-loading]') : null;
        if (btn) setButtonLoading(btn);
    });
    window.addEventListener('pageshow', function (e) { if (e.persisted) resetButtons(); });

    /* ---------- 3. Ảnh bằng chứng bị mất: hiện ô "Ảnh đã mất" thay vì icon vỡ ---------- */
    function markMissing(img) {
        var box = img.closest('.ev-thumb');
        if (box) box.classList.add('is-missing');
    }
    document.addEventListener('error', function (e) {
        if (e.target && e.target.tagName === 'IMG' && e.target.classList.contains('ev-thumb-img')) markMissing(e.target);
    }, true);
    function checkThumbs() {
        document.querySelectorAll('img.ev-thumb-img').forEach(function (img) {
            if (img.complete && img.naturalWidth === 0) markMissing(img);
        });
    }
    document.addEventListener('DOMContentLoaded', checkThumbs);
    window.addEventListener('load', checkThumbs);

    /* ---------- 4. Xem ảnh bằng chứng ngay trên trang (không chuyển trang) ---------- */
    var lb = document.getElementById('evLightbox');
    if (!lb) return;

    var ui = {
        stage: lb.querySelector('.ev-stage'),
        img: document.getElementById('evImg'),
        missing: document.getElementById('evMissing'),
        badge: document.getElementById('evBadge'),
        exam: document.getElementById('evExam'),
        track: document.getElementById('evTrack'),
        time: document.getElementById('evTime'),
        conf: document.getElementById('evConf'),
        desc: document.getElementById('evDesc'),
        download: document.getElementById('evDownload'),
        counter: document.getElementById('evCounter'),
        prev: lb.querySelector('.ev-prev'),
        next: lb.querySelector('.ev-next'),
        close: lb.querySelector('.ev-close')
    };
    var items = [], index = 0, lastFocus = null;

    function readItem(el) {
        var d = el.dataset;
        return {
            src: d.evSrc || '', exam: d.evExam || '', track: d.evTrack || '', type: d.evType || '',
            sev: d.evSev || 'secondary', time: d.evTime || '', conf: d.evConf || '', desc: d.evDesc || ''
        };
    }

    function show(i) {
        if (!items.length) return;
        index = (i + items.length) % items.length;
        var it = items[index];

        ui.badge.className = 'badge fs-6 bg-' + it.sev + '-subtle text-' + it.sev + '-emphasis border border-' + it.sev + '-subtle';
        ui.badge.textContent = it.type;
        ui.exam.textContent = it.exam || '—';
        ui.track.textContent = it.track ? '#' + it.track : '—';
        ui.time.textContent = it.time || '—';
        ui.conf.textContent = it.conf !== '' ? it.conf + '%' : '—';
        ui.desc.textContent = it.desc || '—';
        ui.counter.textContent = (index + 1) + ' / ' + items.length;

        var multi = items.length > 1;
        ui.prev.hidden = !multi;
        ui.next.hidden = !multi;

        ui.missing.hidden = true;
        if (it.src) {
            ui.stage.classList.add('is-loading');
            ui.img.hidden = false;
            ui.img.src = it.src;
            ui.download.href = it.src;
            ui.download.hidden = false;
            // tải trước ảnh kế bên để bấm chuyển ảnh là hiện ngay
            [index - 1, index + 1].forEach(function (n) {
                var nb = items[(n + items.length) % items.length];
                if (nb && nb.src) new Image().src = nb.src;
            });
        } else {
            showMissing();
        }
    }

    function showMissing() {
        ui.stage.classList.remove('is-loading');
        ui.img.hidden = true;
        ui.img.removeAttribute('src');
        ui.missing.hidden = false;
        ui.download.hidden = true;
    }

    ui.img.addEventListener('load', function () { ui.stage.classList.remove('is-loading'); });
    ui.img.addEventListener('error', function () { if (ui.img.getAttribute('src')) showMissing(); });

    function openFrom(el) {
        var group = el.closest('[data-ev-group]') || document;
        var nodes = Array.prototype.slice.call(group.querySelectorAll('[data-evidence]'));
        items = nodes.map(readItem);
        lastFocus = document.activeElement;
        lb.hidden = false;
        document.documentElement.classList.add('ev-open');
        show(Math.max(0, nodes.indexOf(el)));
        ui.close.focus();
    }

    function closeLightbox() {
        lb.hidden = true;
        document.documentElement.classList.remove('ev-open');
        ui.img.removeAttribute('src');
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    document.addEventListener('click', function (e) {
        var row = e.target.closest('[data-evidence]');
        if (!row || lb.contains(row)) return;
        if (e.target.closest('a, button, input, select, textarea, label')) return;
        openFrom(row);
    });
    document.addEventListener('keydown', function (e) {
        if (lb.hidden) {
            var row = e.target.closest && e.target.closest('[data-evidence]');
            if (row && row === e.target && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openFrom(row); }
            return;
        }
        if (e.key === 'Escape') { closeLightbox(); }
        else if (e.key === 'ArrowLeft') { show(index - 1); }
        else if (e.key === 'ArrowRight') { show(index + 1); }
        else if (e.key === 'Tab') {   // giữ phím Tab quay vòng trong cửa sổ
            var f = Array.prototype.filter.call(lb.querySelectorAll('button, a[href]'), function (n) { return !n.hidden && n.offsetParent !== null; });
            if (!f.length) return;
            var first = f[0], last = f[f.length - 1];
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
    });
    lb.addEventListener('click', function (e) {
        if (e.target.closest('[data-ev-close]')) closeLightbox();
    });
    ui.prev.addEventListener('click', function () { show(index - 1); });
    ui.next.addEventListener('click', function () { show(index + 1); });

    // Vuốt trái/phải trên điện thoại
    var touchX = null;
    ui.stage.addEventListener('touchstart', function (e) { touchX = e.touches[0].clientX; }, { passive: true });
    ui.stage.addEventListener('touchend', function (e) {
        if (touchX === null) return;
        var dx = e.changedTouches[0].clientX - touchX;
        touchX = null;
        if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
    });
})();
