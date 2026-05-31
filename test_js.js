
    let currentPallet = null;
    let isSubmitting = false;

    const scannerInput = document.getElementById('splitScannerInput');
    const detailsSection = document.getElementById('splitDetailsSection');
    const scanLoading = document.getElementById('scanLoading');
    const scanError = document.getElementById('scanError');
    const scanErrorMsg = document.getElementById('scanErrorMsg');
    
    // Ustalanie linii ze zmiennej sesyjnej/globalnej z backendu (lub domyślnie PSD)
    const currentLinia = "{{ session.get('aktywna_linia', 'AGRO') }}";

    function resetSplitter() {
        currentPallet = null;
        scannerInput.value = '';
        scannerInput.disabled = false;
        detailsSection.classList.add('d-none');
        scanError.classList.add('d-none');
        document.getElementById('splitWeightInput').value = '';
        scannerInput.focus();
    }

    function showScanError(msg) {
        scanLoading.classList.add('d-none');
        scanError.classList.remove('d-none');
        scanErrorMsg.textContent = msg;
        scannerInput.value = '';
        scannerInput.disabled = false;
        setTimeout(() => scannerInput.focus(), 100);
    }

    async function fetchPalletInfo(sscc) {
        scannerInput.disabled = true;
        scanLoading.classList.remove('d-none');
        scanError.classList.add('d-none');
        detailsSection.classList.add('d-none');

        try {
            const response = await fetch(`/magazyn-dostawy/api/info-paleta?sscc=${encodeURIComponent(sscc)}`);
            const data = await response.json();
            
            scanLoading.classList.add('d-none');

            if (!response.ok || !data.success) {
                showScanError(data.error || 'Nie znaleziono palety.');
                return;
            }

            currentPallet = data.pallet;
            
            document.getElementById('motherSscc').textContent = currentPallet.nr_palety || currentPallet.id;
            document.getElementById('motherProduct').textContent = currentPallet.produkt;
            document.getElementById('motherLocation').textContent = currentPallet.lokalizacja || 'Brak / Nieznana';
            document.getElementById('motherWeight').textContent = currentPallet.waga;
            
            // Ustaw sugerowaną wagę (np. domyślnie puste, żeby pracownik musiał wpisać)
            const weightInput = document.getElementById('splitWeightInput');
            weightInput.value = '';
            weightInput.max = currentPallet.waga;
            
            detailsSection.classList.remove('d-none');
            setTimeout(() => weightInput.focus(), 100);
            
        } catch (err) {
            console.error(err);
            showScanError('Błąd połączenia z serwerem.');
        }
    }

    // Event listeners
    scannerInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
            e.preventDefault();
            const sscc = this.value.trim().replace(/[\r\n]+/g, '');
            if (sscc) fetchPalletInfo(sscc);
        }
    });
    
    document.getElementById('splitCancelBtn').addEventListener('click', resetSplitter);
    
    document.getElementById('splitWeightInput').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) {
            e.preventDefault();
            document.getElementById('splitConfirmBtn').click();
        }
    });

    document.getElementById('splitConfirmBtn').addEventListener('click', async function() {
        if (isSubmitting || !currentPallet) return;
        
        const weightInput = document.getElementById('splitWeightInput');
        const weightToTake = parseFloat(weightInput.value.replace(',', '.'));
        
        if (isNaN(weightToTake) || weightToTake <= 0) {
            alert('Wprowadź prawidłową wagę.');
            weightInput.focus();
            return;
        }
        if (weightToTake >= currentPallet.waga) {
            alert(`Waga do zabrania (${weightToTake} kg) musi być MNIEJSZA niż dostępna waga (${currentPallet.waga} kg). Aby przenieść całą paletę użyj opcji "Przesunięcia".`);
            weightInput.focus();
            return;
        }

        const btn = this;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Zapisywanie...';
        btn.disabled = true;
        isSubmitting = true;

        try {
            const response = await fetch('/magazyn-dostawy/api/podzial-palety', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mother_id: currentPallet.id,
                    mother_table: currentPallet.table,
                    weight_to_take: weightToTake
                })
            });
            const result = await response.json();
            
            if (!response.ok || !result.success) {
                alert(result.error || 'Wystąpił błąd podczas podziału palety.');
                btn.innerHTML = originalText;
                btn.disabled = false;
                isSubmitting = false;
                return;
            }

            // Sukces - odpal druk
            const newPallet = result.new_pallet;
            document.getElementById('newPalletSscc').textContent = newPallet.nr_palety;
            
            // Bezpośredni druk ZPL
            drukujZPLDirect(newPallet.id, newPallet.linia || currentLinia, newPallet.plan_id);

            // Pokaż modal potwierdzenia
            const printModal = new bootstrap.Modal(document.getElementById('printModal'));
            printModal.show();
            
            // Ustaw listener na ponowienie druku
            document.getElementById('forcePrintBtn').onclick = () => {
                drukujZPLDirect(newPallet.id, newPallet.linia || currentLinia, newPallet.plan_id);
            };

        } catch (err) {
            console.error(err);
            alert('Błąd połączenia z serwerem.');
            btn.innerHTML = originalText;
            btn.disabled = false;
            isSubmitting = false;
        }
    });

    // Używamy globalnej funkcji z layoutu, jeśli istnieje. Jeśli nie, tworzymy własny minimalny klient druku.
    function drukujZPLDirect(paleta_id, linia, plan_id) {
        if (!paleta_id) return;
        const printUrl = `/drukuj-zpl/${paleta_id}?linia=${encodeURIComponent(linia || 'AGRO')}&plan_id=${encodeURIComponent(plan_id || '')}`;
        fetch(printUrl)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    console.log('Wysłano do druku:', data);
                } else {
                    console.warn('Błąd druku ZPL:', data.error);
                }
            })
            .catch(err => console.error('Błąd wywołania druku ZPL:', err));
    }
