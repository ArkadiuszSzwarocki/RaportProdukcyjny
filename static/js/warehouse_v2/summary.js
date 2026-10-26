/* QR codes stay local and are generated only for expanded products. */
(function () {
    'use strict';
    function init() {
        const page = document.getElementById('warehouseSummaryPage');
        if (!page || page.dataset.initialized) return;
        page.dataset.initialized = '1';
        const cards = Array.from(page.querySelectorAll('.warehouse-product-card'));
        const search = document.getElementById('summarySearch');
        const type = document.getElementById('summaryType');
        const count = document.getElementById('summaryResultsCount');
        const noResults = document.getElementById('summaryNoResults');
        const dialog = document.getElementById('summaryQrDialog');
        const preview = document.getElementById('summaryQrPreview');
        function draw(target, value, size) {
            target.replaceChildren();
            if (!value || typeof QRCode === 'undefined') {
                target.classList.add('summary-qr-error');
                target.textContent = 'Kod QR jest niedostępny.';
                return false;
            }
            try {
                new QRCode(target, {text: value, width: size, height: size, colorDark: '#000000', colorLight: '#ffffff', correctLevel: QRCode.CorrectLevel.M});
                target.dataset.qrReady = '1';
                return true;
            } catch (error) {
                target.replaceChildren();
                target.textContent = 'Nie można wygenerować kodu QR.';
                target.classList.add('summary-qr-error');
                return false;
            }
        }
        function generateCard(card) {
            if (!card.open || card.dataset.generating === '1') return;
            const pending = Array.from(card.querySelectorAll('[data-qr]')).filter(target => target.dataset.qrReady !== '1');
            card.dataset.generating = '1';
            function batch() {
                if (!card.open || !page.isConnected) { card.dataset.generating = '0'; return; }
                pending.splice(0, 10).forEach(target => draw(target, target.dataset.qr, 64));
                if (pending.length) requestAnimationFrame(batch);
                else card.dataset.generating = '0';
            }
            requestAnimationFrame(batch);
        }
        cards.forEach(card => card.addEventListener('toggle', () => generateCard(card)));
        function filter() {
            const value = search.value.trim().toLocaleLowerCase('pl');
            let visible = 0;
            cards.forEach(card => {
                card.hidden = !card.dataset.name.includes(value) || Boolean(type.value && card.dataset.type !== type.value);
                if (!card.hidden) visible++;
            });
            count.textContent = 'Produkty: ' + visible + ' / ' + cards.length;
            noResults.hidden = visible > 0 || cards.length === 0;
        }
        search.addEventListener('input', filter);
        type.addEventListener('change', filter);
        page.addEventListener('click', event => {
            const button = event.target.closest('[data-qr-value]');
            if (!button || !page.contains(button)) return;
            const value = button.dataset.qrValue;
            document.getElementById('summaryQrText').textContent = value;
            draw(preview, value, Math.min(256, Math.max(128, window.innerWidth - 120)));
            if (!dialog.open) dialog.showModal();
        });
        document.getElementById('closeSummaryQr').addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', event => {
            if (event.target !== dialog) return;
            const bounds = dialog.getBoundingClientRect();
            if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
        });
        dialog.addEventListener('close', () => preview.replaceChildren());
        cards.forEach(generateCard);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
