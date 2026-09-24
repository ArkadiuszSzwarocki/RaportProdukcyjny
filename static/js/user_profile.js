/**
 * Zarządzanie Menu Użytkownika i Modalem Ustawień Osobistych
 */

(function () {
    'use strict';

    let currentProfileData = null;

    // Toggle rozwijanego menu w górnej belce
    function toggleUserProfileMenu(event) {
        if (event) {
            event.stopPropagation();
        }
        const menu = document.getElementById('userProfileMenu');
        const toggle = document.getElementById('userProfileToggle');
        if (!menu) return;

        const isHidden = menu.classList.contains('hidden');
        closeAllDropdowns();

        if (isHidden) {
            menu.classList.remove('hidden');
            menu.setAttribute('aria-hidden', 'false');
            if (toggle) toggle.classList.add('active');
        } else {
            menu.classList.add('hidden');
            menu.setAttribute('aria-hidden', 'true');
            if (toggle) toggle.classList.remove('active');
        }
    }

    function closeAllDropdowns() {
        const menu = document.getElementById('userProfileMenu');
        const toggle = document.getElementById('userProfileToggle');
        if (menu) {
            menu.classList.add('hidden');
            menu.setAttribute('aria-hidden', 'true');
        }
        if (toggle) {
            toggle.classList.remove('active');
        }
    }

    // Zamknij menu po kliknięciu poza nim
    document.addEventListener('click', function (e) {
        const menu = document.getElementById('userProfileMenu');
        const toggle = document.getElementById('userProfileToggle');
        if (menu && !menu.contains(e.target) && (!toggle || !toggle.contains(e.target))) {
            closeAllDropdowns();
        }
    });

    // Otwarcie Modalu Ustawień Osobistych
    function openUserProfileModal(tabName) {
        closeAllDropdowns();
        const modal = document.getElementById('userProfileModal');
        if (!modal) return;

        switchUserProfileTab(tabName || 'profile');
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');

        // Pobierz aktualne dane profilowe z API
        fetchUserProfileData();
    }

    function closeUserProfileModal() {
        const modal = document.getElementById('userProfileModal');
        if (modal) {
            modal.style.display = 'none';
            modal.setAttribute('aria-hidden', 'true');
        }
    }

    // Przełączanie zakładek w modalu
    function switchUserProfileTab(tabName) {
        const tabs = document.querySelectorAll('.profile-tab-btn');
        const contents = document.querySelectorAll('.profile-tab-content');

        tabs.forEach(tab => {
            if (tab.dataset.tab === tabName) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });

        contents.forEach(content => {
            if (content.id === `userProfileTab_${tabName}`) {
                content.classList.add('active');
            } else {
                content.classList.remove('active');
            }
        });
    }

    // Pobieranie danych profilu z API
    function fetchUserProfileData() {
        fetch('/api/user/profile')
            .then(res => res.json())
            .then(data => {
                if (data && data.success && data.profile) {
                    currentProfileData = data.profile;
                    populateUserProfileForm(data.profile);
                }
            })
            .catch(err => {
                console.error('Błąd pobierania danych profilowych:', err);
            });
    }

    // Wypełnianie pól formularza
    function populateUserProfileForm(p) {
        // Tab 1: Dane & Email
        const upLogin = document.getElementById('upLogin');
        const upRola = document.getElementById('upRola');
        const upImieNazwisko = document.getElementById('upImieNazwisko');
        const upEmail = document.getElementById('upEmail');

        if (upLogin) upLogin.value = p.login || '';
        if (upRola) upRola.value = p.rola || '';
        if (upImieNazwisko) upImieNazwisko.value = p.imie_nazwisko || '';
        if (upEmail) upEmail.value = p.email || '';

        // Tab 3: Urlopy
        const upUrlopBiezacy = document.getElementById('upUrlopBiezacy');
        const upUrlopZalegly = document.getElementById('upUrlopZalegly');
        const upLeaveTotal = document.getElementById('upLeaveTotal');
        const upLeaveUsed = document.getElementById('upLeaveUsed');

        if (upUrlopBiezacy) upUrlopBiezacy.value = p.urlop_biezacy !== undefined ? p.urlop_biezacy : 0;
        if (upUrlopZalegly) upUrlopZalegly.value = p.urlop_zalegly !== undefined ? p.urlop_zalegly : 0;
        if (upLeaveTotal) upLeaveTotal.innerText = p.urlop_laczny !== undefined ? p.urlop_laczny : 0;
        if (upLeaveUsed) upLeaveUsed.innerText = p.urlop_wykorzystany !== undefined ? p.urlop_wykorzystany : 0;
    }

    // Zapis ogólnych danych profilu (Email)
    function submitUserProfileGeneral() {
        const btn = document.getElementById('saveGeneralProfileBtn');
        const email = document.getElementById('upEmail').value;

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="material-icons opacity-75">hourglass_empty</span> Zapisywanie...';
        }

        fetch('/api/user/profile/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: email
            })
        })
            .then(res => res.json())
            .then(data => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">save</span> Zapisz dane';
                }
                if (data && data.success) {
                    showToastNotification('✅ ' + data.message, 'success');
                    fetchUserProfileData();
                } else {
                    showToastNotification('⚠️ ' + (data.message || 'Błąd zapisu'), 'error');
                }
            })
            .catch(err => {
                console.error('submitUserProfileGeneral error:', err);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">save</span> Zapisz dane';
                }
                showToastNotification('⚠️ Błąd połączenia z serwerem', 'error');
            });
    }

    // Zapis zmiany hasła
    function submitUserProfilePassword() {
        const oldP = document.getElementById('upOldPassword').value;
        const newP = document.getElementById('upNewPassword').value;
        const repP = document.getElementById('upNewPasswordRepeat').value;
        const btn = document.getElementById('savePasswordBtn');

        if (!oldP || !newP) {
            showToastNotification('Wypełnij wszystkie pola haseł.', 'warning');
            return;
        }
        if (newP !== repP) {
            showToastNotification('Nowe hasła nie są identyczne.', 'warning');
            return;
        }
        if (newP.length < 8) {
            showToastNotification('Nowe hasło musi mieć minimum 8 znaków (w tym litery i cyfry).', 'warning');
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="material-icons opacity-75">hourglass_empty</span> Zmienianie...';
        }

        fetch('/api/zmien-moje-haslo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stare_haslo: oldP,
                nowe_haslo: newP,
                powtorz_nowe_haslo: repP
            })
        })
            .then(res => res.json())
            .then(data => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">vpn_key</span> Zapisz nowe hasło';
                }
                if (data && data.success) {
                    showToastNotification('✅ ' + data.message, 'success');
                    document.getElementById('userProfilePasswordForm').reset();
                } else {
                    showToastNotification('⚠️ ' + (data.message || 'Nie udało się zmienić hasła'), 'error');
                }
            })
            .catch(err => {
                console.error('submitUserProfilePassword error:', err);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">vpn_key</span> Zapisz nowe hasło';
                }
                showToastNotification('⚠️ Błąd połączenia z serwerem', 'error');
            });
    }

    // Zapis ilości urlopu
    function submitUserProfileLeave() {
        const urlopBiezacy = parseInt(document.getElementById('upUrlopBiezacy').value || '0', 10);
        const urlopZalegly = parseInt(document.getElementById('upUrlopZalegly').value || '0', 10);
        const btn = document.getElementById('saveLeaveBtn');

        if (urlopBiezacy < 0 || urlopZalegly < 0) {
            showToastNotification('Liczba dni urlopu nie może być ujemna.', 'warning');
            return;
        }

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="material-icons opacity-75">hourglass_empty</span> Zapisywanie...';
        }

        fetch('/api/user/profile/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                urlop_biezacy: urlopBiezacy,
                urlop_zalegly: urlopZalegly
            })
        })
            .then(res => res.json())
            .then(data => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">save</span> Zaktualizuj urlop';
                }
                if (data && data.success) {
                    showToastNotification('✅ ' + data.message, 'success');
                    fetchUserProfileData();
                } else {
                    showToastNotification('⚠️ ' + (data.message || 'Błąd aktualizacji urlopu'), 'error');
                }
            })
            .catch(err => {
                console.error('submitUserProfileLeave error:', err);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="material-icons">save</span> Zaktualizuj urlop';
                }
                showToastNotification('⚠️ Błąd połączenia z serwerem', 'error');
            });
    }

    // Pomocnicza funkcja toastów
    function showToastNotification(msg, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(msg, type || 'info');
        } else {
            alert(msg);
        }
    }

    // Wyeksportuj funkcje globalnie
    window.toggleUserProfileMenu = toggleUserProfileMenu;
    window.openUserProfileModal = openUserProfileModal;
    window.closeUserProfileModal = closeUserProfileModal;
    window.switchUserProfileTab = switchUserProfileTab;
    window.submitUserProfileGeneral = submitUserProfileGeneral;
    window.submitUserProfilePassword = submitUserProfilePassword;
    window.submitUserProfileLeave = submitUserProfileLeave;

    // Kompatybilność wsteczna dla openChangeMyPasswordModal
    window.openChangeMyPasswordModal = function () {
        openUserProfileModal('password');
    };
})();
