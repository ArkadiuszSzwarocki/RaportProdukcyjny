/**
 * Scanner UI Multi-language Translator (PL / UA / EN)
 * Allows real-time switching of language on mobile scanner interfaces.
 */

(function (global) {
    'use strict';

    const DICTIONARIES = {
        pl: {
            scan_code: "Zeskanuj kod kreskowy / SSCC",
            invalid_batch: "Niezgodność partii!",
            pallet_blocked: "Paleta zablokowana!",
            weight_ok: "Waga poprawna",
            quantity_missing: "Niekompletny załadunek!",
            offline_mode: "Tryb offline",
            synced: "Zsynchronizowano",
            confirm: "Zatwierdź",
            cancel: "Anuluj",
            loading: "Ładowanie danych...",
            fifo_warning: "Uwaga: Dostępna jest starsza partia (FIFO)!"
        },
        ua: {
            scan_code: "Відскануйте штрих-код / SSCC",
            invalid_batch: "Невідповідність партії!",
            pallet_blocked: "Піддон заблоковано!",
            weight_ok: "Вага вірна",
            quantity_missing: "Неповне завантаження!",
            offline_mode: "Автономний режим (Офлайн)",
            synced: "Синхронізовано",
            confirm: "Підтвердити",
            cancel: "Скасувати",
            loading: "Завантаження даних...",
            fifo_warning: "Увага: Доступна старіша партія (FIFO)!"
        },
        en: {
            scan_code: "Scan barcode / SSCC",
            invalid_batch: "Batch mismatch!",
            pallet_blocked: "Pallet is blocked!",
            weight_ok: "Weight verified",
            quantity_missing: "Incomplete dispatch!",
            offline_mode: "Offline mode",
            synced: "Synchronized",
            confirm: "Confirm",
            cancel: "Cancel",
            loading: "Loading data...",
            fifo_warning: "Warning: Older batch available (FIFO)!"
        }
    };

    class ScannerI18n {
        constructor() {
            this.currentLang = localStorage.getItem('rp_scanner_lang') || 'pl';
        }

        setLanguage(lang) {
            if (DICTIONARIES[lang]) {
                this.currentLang = lang;
                localStorage.setItem('rp_scanner_lang', lang);
                this.applyTranslations();
            }
        }

        t(key) {
            const dict = DICTIONARIES[this.currentLang] || DICTIONARIES.pl;
            return dict[key] || key;
        }

        applyTranslations() {
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (key) {
                    el.innerText = this.t(key);
                }
            });
            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const key = el.getAttribute('data-i18n-placeholder');
                if (key) {
                    el.setAttribute('placeholder', this.t(key));
                }
            });
        }
    }

    global.scannerI18n = new ScannerI18n();
})(window);
