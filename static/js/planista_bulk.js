  (function () {
    const globalOpakowania = window.PlanistaBulkConfig.data.opakowania;
    const globalEtykiety = window.PlanistaBulkConfig.data.etykiety;

    function getStripeBadgeHtml(name) {
      if (!name || name === '-' || name === '-- Brak / Nie określono --') return '';
      let color = '';
      let border = '1px solid #ccc';
      const norm = name.toLowerCase();
      if (norm.includes('czerwon')) {
        color = '#dc2626';
        border = '1px solid #b91c1c';
      } else if (norm.includes('fioletow')) {
        color = '#800080';
        border = '1px solid #6a006a';
      } else if (norm.includes('brązow') || norm.includes('brazow')) {
        color = '#8B4513';
        border = '1px solid #5c2d0c';
      } else if (norm.includes('żółt') || norm.includes('zolt')) {
        color = '#FFD700';
        border = '1px solid #ccab00';
      } else if (norm.includes('biał') || norm.includes('bial')) {
        color = '#ffffff';
        border = '1px solid #cbd5e1';
      } else {
        return '';
      }
      return `<span class="stripe-badge" style="background-color: ${color}; border: ${border}; display: inline-block; width: 30px; height: 12px; border-radius: 2px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.15); vertical-align: middle; margin-left: 6px;"></span>`;
    }

    // Initialize searchable selects for packaging & labels
    setTimeout(function() {
      initSearchableSelect('inpOpakowanie', 'inpOpakowanie_search', 'inpOpakowanie_dropdown', 'inpOpakowanie_indicator', globalOpakowania, false);
      initSearchableSelect('inpEtykieta', 'inpEtykieta_search', 'inpEtykieta_dropdown', 'inpEtykieta_indicator', globalEtykiety, true);
    }, 100);

    const tbody = document.querySelector('#bulkTable tbody');
    const bulkTable = document.querySelector('#bulkTable');
    const emptyState = document.querySelector('#emptyState');
    const selectProdukt = document.getElementById('selectProdukt');
    const modalBackdrop = document.getElementById('productModalBackdrop');
    const productModal = document.getElementById('productModal');
    const btnAddNewProduct = document.getElementById('btnAddNewProduct');
    const btnCancelModal = document.getElementById('btnCancelModal');
    const btnSaveProduct = document.getElementById('btnSaveProduct');
    const btnCancel = document.getElementById('btnCancel');
    const newProductForm = document.getElementById('newProductForm');
    const btnManageProducts = document.getElementById('btnManageProducts');
    const manageModalBackdrop = document.getElementById('manageModalBackdrop');
    const manageModal = document.getElementById('manageModal');
    const productsList = document.getElementById('productsList');
    const sekcjaSelect = document.getElementById('sekcja_select');
    const agroFieldsContainer = document.getElementById('agroFieldsContainer');
    const packagingTypeRow = document.getElementById('packagingTypeRow');
    const inpTypOpakowania = document.getElementById('inpTypOpakowania');
    const inpTermin = document.getElementById('inpTermin');
    const customTerminContainer = document.getElementById('customTerminContainer');

    const btnRaportDnia = document.getElementById('btnRaportDnia');
    const raportDniaModalBackdrop = document.getElementById('raportDniaModalBackdrop');
    const raportDniaModal = document.getElementById('raportDniaModal');
    const raportDniaContent = document.getElementById('raportDniaContent');
    const btnRaportDniaClose = document.getElementById('btnRaportDniaClose');
    const btnRaportDniaCloseBottom = document.getElementById('btnRaportDniaCloseBottom');

    function closeRaportDniaModal() {
      if(raportDniaModalBackdrop) raportDniaModalBackdrop.style.display = 'none';
      if(raportDniaModal) {
          raportDniaModal.style.display = 'none';
          raportDniaModal.style.flexDirection = 'column';
      }
    }

    if (btnRaportDnia) {
      btnRaportDnia.addEventListener('click', function() {
        if(raportDniaModalBackdrop) raportDniaModalBackdrop.style.display = 'block';
        if(raportDniaModal) {
            raportDniaModal.style.display = 'flex';
        }
        
        const dataPlanu = document.getElementById('data_planu').value;
        const linia = (sekcjaSelect.value === 'Agro') ? 'AGRO' : 'PSD';
        
        raportDniaContent.innerHTML = '<div style="text-align: center; padding: 20px; color: #64748b;">Ładowanie danych...</div>';
        
        fetch(`/planista/api/raport_dnia?data=${dataPlanu}&linia=${linia}`)
          .then(res => res.json())
          .then(data => {
            if (data.error || data.message || data.success === false) {
              const errorMsg = data.error || data.message || "Wystąpił nieznany błąd";
              raportDniaContent.innerHTML = `<div style="color: red; padding: 20px; text-align: center;">Błąd: ${errorMsg}</div>`;
              return;
            }
            
            let html = `
              <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                <div style="flex: 1; background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
                  <div style="font-size: 0.85em; color: #64748b; margin-bottom: 5px;">Pełna suma wyprodukowanych palet</div>
                  <div style="font-size: 1.5em; font-weight: 700; color: #0f172a;">${data.total_palet} szt.</div>
                </div>
                <div style="flex: 1; background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
                  <div style="font-size: 0.85em; color: #64748b; margin-bottom: 5px;">Łączna waga</div>
                  <div style="font-size: 1.5em; font-weight: 700; color: #0f172a;">${data.total_waga} kg</div>
                </div>
              </div>
              <h4 style="margin: 0 0 10px 0; color: #334155;">Rozbicie na zlecenia:</h4>
            `;
            
            if (!data.items || data.items.length === 0) {
              html += '<div style="padding: 20px; text-align: center; color: #94a3b8;">Brak wyprodukowanych palet w tym dniu.</div>';
            } else {
              html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.95em;">';
              html += '<thead style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;"><tr>';
              html += '<th style="padding: 10px; text-align: left;">Zlecenie</th>';
              html += '<th style="padding: 10px; text-align: center;">Ilość palet</th>';
              html += '<th style="padding: 10px; text-align: right;">Suma Wagi (kg)</th>';
              html += '</tr></thead><tbody>';
              
              data.items.forEach(item => {
                html += `<tr style="border-bottom: 1px solid #e2e8f0;">`;
                html += `<td style="padding: 10px; color: #334155;"><strong>${item.produkt}</strong> <span style="color: #94a3b8; font-size: 0.85em;">(#${item.plan_id})</span></td>`;
                html += `<td style="padding: 10px; text-align: center; font-weight: 600;">${item.ilosc_palet}</td>`;
                html += `<td style="padding: 10px; text-align: right; color: #0284c7;">${item.laczna_waga || 0}</td>`;
                html += `</tr>`;
              });
              
              html += '</tbody></table>';
            }
            
            raportDniaContent.innerHTML = html;
          })
          .catch(err => {
            console.error('Error fetching raport dnia:', err);
            raportDniaContent.innerHTML = `<div style="color: red; padding: 20px; text-align: center;">Błąd pobierania danych.</div>`;
          });
      });
    }

    if (btnRaportDniaClose) btnRaportDniaClose.addEventListener('click', closeRaportDniaModal);
    if (btnRaportDniaCloseBottom) btnRaportDniaCloseBottom.addEventListener('click', closeRaportDniaModal);
    if (raportDniaModalBackdrop) raportDniaModalBackdrop.addEventListener('click', closeRaportDniaModal);

    window.toggleCustomTermin = function() {
      if (inpTermin && inpTermin.value === 'inna') {
        customTerminContainer.style.display = 'block';
        document.getElementById('inpTerminCustom').required = true;
      } else {
        customTerminContainer.style.display = 'none';
        document.getElementById('inpTerminCustom').required = false;
        document.getElementById('inpTerminCustom').value = '';
      }
    };

    // Planning info elements
    const planningInfoBanner = document.getElementById('planningInfoBanner');
    const btnOpenPlanningInfo = document.getElementById('btnOpenPlanningInfo');
    const infoModal = document.getElementById('infoModal');
    const infoModalBackdrop = document.getElementById('infoModalBackdrop');
    const btnDismissInfo = document.getElementById('btnDismissInfo');

    const currentLogin = window.PlanistaBulkConfig.data.userLogin;
    const storageKey = `planista_bulk_info_read_${currentLogin}`;

    const checkInfoBanner = () => {
      if (localStorage.getItem(storageKey) !== 'true') {
        planningInfoBanner.style.display = 'flex';
      } else {
        planningInfoBanner.style.display = 'none';
      }
    };

    let produktyList = [];
    let editProductId = null;

    // Load produkty from API
    const loadProdukty = (callback = null) => {
      fetch('/api/produkty')
        .then(r => r.json())
        .then(data => {
          if (data.success && data.produkty) {
            produktyList = data.produkty;
            updateProduktySelect();
            if (callback) callback();
          }
        })
        .catch(e => console.error('Error loading produkty:', e));
    };

    // Update dropdown with produkty
    const updateProduktySelect = () => {
      filterAndShowProdukty('');
    };

    // Filter produkty based on search term
    const filterAndShowProdukty = (searchTerm) => {
      const dropdown = document.getElementById('produktyDropdown');

      // If search term is empty, close dropdown
      if (!searchTerm || searchTerm.trim() === '') {
        dropdown.style.display = 'none';
        return;
      }

      const filtered = produktyList.filter(p => 
        p.nazwa_produktu.toLowerCase().includes(searchTerm.toLowerCase())
      );

      if (filtered.length === 0) {
        dropdown.innerHTML = '<div style="padding: 8px 12px; color: #999;">Brak wyników</div>';
        dropdown.style.display = 'block';
        return;
      }

      dropdown.innerHTML = filtered.map(p => `
        <div class="produkty-dropdown-item" data-produkt="${p.nazwa_produktu}">
          <div>
            <div class="produkty-dropdown-item-name">${p.nazwa_produktu}</div>
            <div class="produkty-dropdown-item-nr">${p.nr_receptury ? 'Nr: ' + p.nr_receptury : ''}</div>
          </div>
        </div>
      `).join('');

      // Add click handlers to dropdown items
      dropdown.querySelectorAll('.produkty-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
          const produkt = item.getAttribute('data-produkt');
          selectProdukt.value = produkt;
          selectProdukt.dispatchEvent(new Event('change'));
          dropdown.style.display = 'none';
        });
      });

      dropdown.style.display = 'block';
    };

    // Handle product input/search
    selectProdukt.addEventListener('input', (e) => {
      filterAndShowProdukty(e.target.value);
    });

    // Handle product selection to auto-fill values
    selectProdukt.addEventListener('change', () => {
      if (selectProdukt.value) {
        const selectedProduct = produktyList.find(p => p.nazwa_produktu === selectProdukt.value);
        if (selectedProduct) {
          document.getElementById('inpNr').value = selectedProduct.nr_receptury || '';
          document.getElementById('inpTyp').value = selectedProduct.typ_produkcji || 'worki_zgrzewane_25';

          // Auto-fill AGRO packaging and label if they exist
          if (selectedProduct.opakowanie_id && window.setSearchableSelectValue && window.setSearchableSelectValue['inpOpakowanie']) {
            window.setSearchableSelectValue['inpOpakowanie'](selectedProduct.opakowanie_id);
          } else if (window.clearSearchableSelects && window.clearSearchableSelects['inpOpakowanie']) {
            window.clearSearchableSelects['inpOpakowanie']();
          }

          if (selectedProduct.etykieta_id && window.setSearchableSelectValue && window.setSearchableSelectValue['inpEtykieta']) {
            window.setSearchableSelectValue['inpEtykieta'](selectedProduct.etykieta_id);
          } else if (window.clearSearchableSelects && window.clearSearchableSelects['inpEtykieta']) {
            window.clearSearchableSelects['inpEtykieta']();
          }
        }
      }
      // Odśwież widoczność pól po zmianie produktu (może być czyszczenie)
      toggleAgroFields();
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.produkty-container')) {
        document.getElementById('produktyDropdown').style.display = 'none';
      }
    });

    // Handle Enter key in input
    selectProdukt.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const dropdown = document.getElementById('produktyDropdown');
        const firstItem = dropdown.querySelector('.produkty-dropdown-item');
        if (firstItem) {
          firstItem.click();
        }
      }
    });

    // Modal functions
    const openProductModal = (productToEdit = null) => {
      // Dynamic loading of packaging select options
      const packagingSelect = document.getElementById('newProductOpakowanie');
      const etykietaSelect = document.getElementById('newProductEtykieta');

      if (packagingSelect.options.length <= 1) {
        globalOpakowania.forEach(o => {
          const opt = document.createElement('option');
          opt.value = o.id;
          opt.textContent = o.nazwa;
          packagingSelect.appendChild(opt);
        });
      }

      if (etykietaSelect.options.length <= 1) {
        globalEtykiety.forEach(e => {
          const opt = document.createElement('option');
          opt.value = e.id;
          opt.textContent = e.nazwa;
          etykietaSelect.appendChild(opt);
        });
      }

      if (productToEdit) {
        editProductId = productToEdit.id;
        document.getElementById('productModalTitle').textContent = '✏️ Edytuj produkt';
        btnSaveProduct.textContent = 'Zapisz zmiany';

        document.getElementById('newProductName').value = productToEdit.nazwa_produktu || '';
        document.getElementById('newProductNr').value = productToEdit.nr_receptury || '';
        document.getElementById('newProductTyp').value = productToEdit.typ_produkcji || 'worki_zgrzewane_25';
        document.getElementById('newProductOpakowanie').value = productToEdit.opakowanie_id || '';
        document.getElementById('newProductEtykieta').value = productToEdit.etykieta_id || '';

        // Hide manage modal temporarily
        manageModal.classList.remove('active');
        manageModalBackdrop.classList.remove('active');
      } else {
        editProductId = null;
        document.getElementById('productModalTitle').textContent = '➕ Dodaj nowy produkt';
        btnSaveProduct.textContent = 'Dodaj produkt';
        
        newProductForm.reset();
      }

      modalBackdrop.classList.add('active');
      productModal.classList.add('active');
      document.getElementById('newProductName').focus();
    };

    const closeProductModal = () => {
      modalBackdrop.classList.remove('active');
      productModal.classList.remove('active');
      newProductForm.reset();

      // If we were editing from manage list, return back to manage modal
      if (editProductId !== null) {
        const prevId = editProductId;
        editProductId = null;
        setTimeout(() => {
          manageModalBackdrop.classList.add('active');
          manageModal.classList.add('active');
          loadProductsForManagement();
        }, 200);
      } else {
        editProductId = null;
      }
    };

    // Save product (Add or Edit)
    btnSaveProduct.addEventListener('click', () => {
      const nazwa = (document.getElementById('newProductName').value || '').trim();
      const nr = (document.getElementById('newProductNr').value || '').trim();
      const typ = document.getElementById('newProductTyp').value;
      const opakowanie_id = document.getElementById('newProductOpakowanie').value ? parseInt(document.getElementById('newProductOpakowanie').value) : null;
      const etykieta_id = document.getElementById('newProductEtykieta').value ? parseInt(document.getElementById('newProductEtykieta').value) : null;

      if (!nazwa) {
        return safeAlert('Błąd', 'Podaj nazwę produktu');
      }

      const payload = {
        nazwa_produktu: nazwa,
        nr_receptury: nr,
        typ_produkcji: typ,
        opakowanie_id: opakowanie_id,
        etykieta_id: etykieta_id
      };

      const url = editProductId ? `/api/produkty/${editProductId}` : '/api/produkty';
      const method = editProductId ? 'PUT' : 'POST';

      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(r => r.json())
        .then(data => {
          if (data.success) {
            safeAlert('Sukces', editProductId ? '✅ Zmiany zostały zapisane!' : '✅ Produkt "' + nazwa + '" dodany do listy!');
            loadProdukty(() => {
              closeProductModal();
            });
            if (!editProductId) {
              setTimeout(() => {
                selectProdukt.value = nazwa;
                selectProdukt.focus();
                selectProdukt.dispatchEvent(new Event('input'));
                selectProdukt.dispatchEvent(new Event('change'));
              }, 100);
            }
          } else {
            safeAlert('Błąd', '❌ Błąd: ' + data.message);
          }
        })
        .catch(e => {
          console.error('Error:', e);
          safeAlert('Błąd sieci', 'Błąd sieci');
        });
    });

    btnAddNewProduct.addEventListener('click', openProductModal);
    btnCancelModal.addEventListener('click', closeProductModal);
    if (btnCancel) btnCancel.addEventListener('click', () => {
      window.location.href = window.PlanistaBulkConfig.urls.panelPlanisty + "?data=" + encodeURIComponent(window.PlanistaBulkConfig.data.wybranaData);
    });
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) {
        closeProductModal();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (productModal.classList.contains('active')) {
          closeProductModal();
        } else if (infoModal && infoModal.classList.contains('active')) {
          closeInfoModal();
        }
      }
    });

    function updateTableVisibility() {
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const planCount = document.getElementById('planCount');
      const submitBtn = document.getElementById('btnSubmitAll');
      
      if (rows.length === 0) {
        bulkTable.style.display = 'none';
        emptyState.style.display = 'block';
        if (planCount) planCount.textContent = '';
        if (submitBtn) submitBtn.style.display = 'none';
      } else {
        bulkTable.style.display = 'table';
        emptyState.style.display = 'none';
        if (planCount) planCount.textContent = `Ilość planów: ${rows.length}`;
        if (submitBtn) submitBtn.style.display = 'inline-block';
      }
    }

    function togglePackagingFields() {
      // Kontrola widoczności pól opakowanie/etykieta w zależności od typ_opakowania
      if (!agroFieldsContainer) return;
      
      const isAgro = sekcjaSelect && sekcjaSelect.value === 'Agro';
      const isCzyszczenie = selectProdukt && (selectProdukt.value || '').toLowerCase().includes('czyszczenie');
      const typOpakowania = inpTypOpakowania ? inpTypOpakowania.value : 'worki';
      
      // Dla big bag ukrywamy pola opakowanie i etykieta
      if (typOpakowania === 'bigbag') {
        agroFieldsContainer.style.display = 'none';
      } else if (isAgro && !isCzyszczenie) {
        agroFieldsContainer.style.display = 'block';
      }
    }

    function toggleAgroFields() {
      const isAgro = sekcjaSelect && sekcjaSelect.value === 'Agro';
      const isCzyszczenie = selectProdukt && (selectProdukt.value || '').toLowerCase().includes('czyszczenie');
      
      const pageTitle = document.getElementById('bulkPageTitle');
      if (pageTitle) {
        pageTitle.innerHTML = isAgro ? '📥 Dodawanie wielu zleceń dla produkcji AGRO' : '📥 Dodawanie wielu zleceń dla produkcji PSD';
      }
      
      // Pokazuj pole typ_opakowania dla AGRO, ale NIE dla czyszczenia
      if (packagingTypeRow) {
        if (isAgro && !isCzyszczenie) {
          packagingTypeRow.style.display = 'block';
        } else {
          packagingTypeRow.style.display = 'none';
        }
      }
      
      if (agroFieldsContainer) {
        if (isAgro && !isCzyszczenie) {
          togglePackagingFields(); // Kontroluj widoczność na podstawie typu opakowania
          
          // Re-trigger autofill when section changes to Agro
          if (selectProdukt.value) {
            const selectedProduct = produktyList.find(p => p.nazwa_produktu === selectProdukt.value);
            if (selectedProduct) {
              if (selectedProduct.opakowanie_id && window.setSearchableSelectValue && window.setSearchableSelectValue['inpOpakowanie']) {
                window.setSearchableSelectValue['inpOpakowanie'](selectedProduct.opakowanie_id);
              }
              if (selectedProduct.etykieta_id && window.setSearchableSelectValue && window.setSearchableSelectValue['inpEtykieta']) {
                window.setSearchableSelectValue['inpEtykieta'](selectedProduct.etykieta_id);
              }
            }
          }
        } else {
          agroFieldsContainer.style.display = 'none';
          if (window.clearSearchableSelects) {
            if (window.clearSearchableSelects['inpOpakowanie']) window.clearSearchableSelects['inpOpakowanie']();
            if (window.clearSearchableSelects['inpEtykieta']) window.clearSearchableSelects['inpEtykieta']();
          }
        }
      }

      // Show/hide worek/etykieta columns in bulk table headers and rows
      if (bulkTable) {
        const thWorek = bulkTable.querySelector('th.col-worek');
        const thEtykieta = bulkTable.querySelector('th.col-etykieta');
        if (thWorek) thWorek.style.display = isAgro ? '' : 'none';
        if (thEtykieta) thEtykieta.style.display = isAgro ? '' : 'none';

        const tdWoreks = bulkTable.querySelectorAll('td.col-worek');
        const tdEtykietas = bulkTable.querySelectorAll('td.col-etykieta');
        tdWoreks.forEach(td => td.style.display = isAgro ? '' : 'none');
        tdEtykietas.forEach(td => td.style.display = isAgro ? '' : 'none');
      }
    }

    if (sekcjaSelect) {
      sekcjaSelect.addEventListener('change', toggleAgroFields);
      // Run immediately on page load to set correct initial state
      setTimeout(toggleAgroFields, 50);
    }
    
    if (inpTypOpakowania) {
      inpTypOpakowania.addEventListener('change', togglePackagingFields);
    }

    const addRow = () => {
      const produkt = selectProdukt.value.trim();
      const nr = document.getElementById('inpNr').value.trim();
      const tonazVal = document.getElementById('inpTonaz').value;
      const tonaz = tonazVal === '' ? null : (parseFloat(tonazVal) || 0);
      const typ = document.getElementById('inpTyp').value;
      const typOpakowania = inpTypOpakowania ? inpTypOpakowania.value : 'worki';

      const rodzajPaletyEl = document.getElementById('inpRodzajPalety');
      const rodzajPalety = rodzajPaletyEl ? rodzajPaletyEl.value : 'krajowa';

      let termin = inpTermin ? inpTermin.value : '';
      if (termin === 'inna') {
        const customDate = document.getElementById('inpTerminCustom').value;
        if (!customDate) { return safeAlert('Błąd', 'Podaj datę przydatności'); }
        termin = customDate;
      }

      if (!produkt) { return safeAlert('Błąd', 'Wybierz produkt ze listy'); }
      if (tonaz === null || tonaz <= 0) { return safeAlert('Błąd', 'Podaj poprawną wagę (kg) większą od 0'); }

      const isAgro = sekcjaSelect && sekcjaSelect.value === 'Agro';
      const isCzyszczenie = produkt.toLowerCase().includes('czyszczenie');
      let opakowanieId = '';
      let opakowanieNazwa = '';
      let etykietaId = '';
      let etykietaNazwa = '';

      if (isAgro && !isCzyszczenie && typOpakowania === 'worki') {
        // Dla worków wymagane są opakowanie i etykieta
        const inpOpak = document.getElementById('inpOpakowanie');
        const inpEtyk = document.getElementById('inpEtykieta');
        const inpOpakSearch = document.getElementById('inpOpakowanie_search');
        const inpEtykSearch = document.getElementById('inpEtykieta_search');
        if (!inpOpak || !inpEtyk || !inpOpak.value || !inpEtyk.value) {
          return safeAlert('Błąd', 'Dla sekcji AGRO z workami wybór worka oraz etykiety jest obowiązkowy!');
        }
        opakowanieId = inpOpak.value;
        opakowanieNazwa = inpOpakSearch.value;
        etykietaId = inpEtyk.value;
        etykietaNazwa = inpEtykSearch.value;
      }

      const tr = document.createElement('tr');
      const etykietaBadge = isAgro ? getStripeBadgeHtml(etykietaNazwa) : '';
      const rodzajPaletyCellHtml = rodzajPalety === 'eksportowa'
        ? '<span style="display:inline-flex;align-items:center;gap:4px;background:linear-gradient(135deg,#ff4500,#ff6b00);color:#fff;border-radius:999px;padding:2px 10px;font-size:0.75rem;font-weight:800;letter-spacing:0.04em;">🚢 EKSPORT</span>'
        : '<span style="color:#64748b;font-size:0.85rem;">🏠 krajowa</span>';
      tr.innerHTML = `<td><strong>${produkt}</strong></td>` +
                     `<td>${nr}</td>` +
                     `<td>${tonaz}</td>` +
                     `<td>${typ}</td>` +
                     `<td>${rodzajPaletyCellHtml}</td>` +
                     `<td>${termin}</td>` +
                     `<td class="col-worek" style="${isAgro ? '' : 'display: none;'}">${opakowanieNazwa}</td>` +
                     `<td class="col-etykieta" style="${isAgro ? '' : 'display: none;'}"><span style="display: inline-flex; align-items: center; gap: 6px;">${etykietaNazwa} ${etykietaBadge}</span></td>` +
                     `<td><button type="button" class="delete-button">🗑️</button></td>`;
      
      tr.dataset.produkt = produkt;
      tr.dataset.nr = nr;
      tr.dataset.tonaz = tonaz;
      tr.dataset.typ = typ;
      tr.dataset.typOpakowania = typOpakowania;
      tr.dataset.rodzaj_palety = rodzajPalety;
      tr.dataset.terminPrzydatnosci = termin;
      if (isAgro) {
        tr.dataset.opakowanieId = opakowanieId;
        tr.dataset.opakowanieNazwa = opakowanieNazwa;
        tr.dataset.etykietaId = etykietaId;
        tr.dataset.etykietaNazwa = etykietaNazwa;
      }

      tbody.appendChild(tr);

      selectProdukt.value = '';
      document.getElementById('inpNr').value = '';
      document.getElementById('inpTonaz').value = '';
      if (rodzajPaletyEl) rodzajPaletyEl.value = 'krajowa';
      document.getElementById('inpTyp').value = 'worki_zgrzewane_25';
      if (isAgro) {
        if (window.clearSearchableSelects) {
          if (window.clearSearchableSelects['inpOpakowanie']) window.clearSearchableSelects['inpOpakowanie']();
          if (window.clearSearchableSelects['inpEtykieta']) window.clearSearchableSelects['inpEtykieta']();
        }
      }

      updateTableVisibility();
      updateSubmitState();
    };

    const btnAddRow = document.getElementById('btnAddRow');
    if (btnAddRow) btnAddRow.addEventListener('click', addRow);

    document.getElementById('inpTonaz').addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addRow();
      }
    });

    tbody.addEventListener('click', function (e) {
      if (e.target.classList.contains('delete-button')) {
        e.target.closest('tr').remove();
        updateTableVisibility();
        updateSubmitState();
      }
    });

    const submitBtn = document.getElementById('btnSubmitAll');

    function validateRows(rows) {
      const sekcja = sekcjaSelect ? sekcjaSelect.value : '';
      for (let i = 0; i < rows.length; i++) {
        const r = rows[i];
        const produkt = (r.dataset.produkt || '').trim();
        const ton = parseFloat(r.dataset.tonaz) || 0;
        const typ = (r.dataset.typ || '').trim();
        if (!produkt) return { ok: false, message: `Wiersz ${i + 1}: brak produktu` };
        if (!typ) return { ok: false, message: `Wiersz ${i + 1}: brak typu produkcji` };
        if (!(ton > 0)) return { ok: false, message: `Wiersz ${i + 1}: waga (kg) powinna być większa niż 0` };
        if (sekcja === 'Agro') {
          if (!r.dataset.opakowanieId || !r.dataset.etykietaId) {
            return { ok: false, message: `Wiersz ${i + 1}: brak wybranego worka lub etykiety dla zlecenia AGRO` };
          }
        }
      }
      return { ok: true };
    }

    function updateSubmitState() {
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const v = validateRows(rows);
      submitBtn.disabled = !(rows.length > 0 && v.ok);
    }

    const btnSubmitAll = document.getElementById('btnSubmitAll');
    if (btnSubmitAll) btnSubmitAll.addEventListener('click', function () {
      const rows = Array.from(tbody.querySelectorAll('tr'));
      if (rows.length === 0) return safeAlert('Błąd', 'Brak dodanych zleceń');
      const valid = validateRows(rows);
      if (!valid.ok) return safeAlert('Błąd', valid.message);

      const data_planu = document.getElementById('data_planu').value || window.PlanistaBulkConfig.data.wybranaData;
      const sekcja = sekcjaSelect ? sekcjaSelect.value : '';
      const payload = rows.map(r => ({
        produkt: r.dataset.produkt,
        nr_receptury: r.dataset.nr,
        tonaz: parseFloat(r.dataset.tonaz) || 0,
        rodzaj_palety: r.dataset.rodzaj_palety || 'krajowa',
        typ_produkcji: r.dataset.typ,
        typ_opakowania: r.dataset.typOpakowania || 'worki',
        sekcja: sekcja,
        termin_przydatnosci: r.dataset.terminPrzydatnosci,
        opakowanie_id: r.dataset.opakowanieId ? parseInt(r.dataset.opakowanieId) : null,
        etykieta_id: r.dataset.etykietaId ? parseInt(r.dataset.etykietaId) : null
      }));

      fetch(window.PlanistaBulkConfig.urls.dodajPlanyBatch, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ data_planu: data_planu, plans: payload })
      })
        .then(r => r.json())
        .then(j => {
          if (j && j.success) {
            const sekcja = document.getElementById('sekcja_select').value;
            const tab = sekcja.toLowerCase() === 'agro' ? 'agro' : 'psd';
            window.location = window.PlanistaBulkConfig.urls.panelPlanisty + "?data=" + encodeURIComponent(data_planu) + "&tab=" + tab;
            } else {
            safeAlert('Błąd', j && j.message ? j.message : 'Błąd serwera');
          }
        })
        .catch(e => {
          console.error(e);
          safeAlert('Błąd sieci', 'Błąd sieci');
        });
    });

    // Products Management Functions
    const loadProductsForManagement = () => {
      const searchInp = document.getElementById('manageSearchInput');
      const filterTerm = searchInp ? (searchInp.value || '').trim().toLowerCase() : '';
      
      const filtered = produktyList.filter(product => {
        const nameMatch = (product.nazwa_produktu || '').toLowerCase().includes(filterTerm);
        const nrMatch = (product.nr_receptury || '').toLowerCase().includes(filterTerm);
        return nameMatch || nrMatch;
      });

      if (filtered.length === 0) {
        productsList.innerHTML = '<div style="text-align: center; padding: 40px; color: #999; font-size: 15px;">Brak produktów spełniających kryteria</div>';
        return;
      }

      let html = `
        <table class="modern-table" style="width: 100%; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #475569; text-transform: uppercase; letter-spacing: 0.5px;">
              <th style="padding: 12px 10px; font-weight: 600;">Nazwa produktu</th>
              <th style="padding: 12px 10px; font-weight: 600; width: 120px;">Nr receptury</th>
              <th style="padding: 12px 10px; font-weight: 600; width: 150px;">Typ produkcji</th>
              <th style="padding: 12px 10px; font-weight: 600;">Domyślny worek / etykieta</th>
              <th style="padding: 12px 10px; font-weight: 600; text-align: right; width: 160px;">Akcje</th>
            </tr>
          </thead>
          <tbody>
      `;

      filtered.forEach(product => {
        const opakowanie = product.opakowanie_id ? (globalOpakowania.find(o => o.id === product.opakowanie_id)?.nazwa || '-') : '-';
        const etykieta = product.etykieta_id ? (globalEtykiety.find(e => e.id === product.etykieta_id)?.nazwa || '-') : '-';
        const etykietaBadge = product.etykieta_id ? getStripeBadgeHtml(etykieta) : '';
        
        let typDisplay = '';
        if (product.typ_produkcji === 'worki_zgrzewane_25') typDisplay = 'Worki 25 kg';
        else if (product.typ_produkcji === 'worki_zgrzewane_20') typDisplay = 'Worki 20 kg';
        else if (product.typ_produkcji === 'worki_zszywane_25') typDisplay = 'Szyte 25 kg';
        else if (product.typ_produkcji === 'worki_zszywane_20') typDisplay = 'Szyte 20 kg';
        else if (product.typ_produkcji === 'bigbag') typDisplay = 'BigBag';
        else typDisplay = product.typ_produkcji || '-';

        html += `
          <tr class="product-table-row" style="border-bottom: 1px solid #f1f5f9; transition: background 0.15s;">
            <td style="padding: 12px 10px; font-weight: 600; color: #1e293b;">${product.nazwa_produktu}</td>
            <td style="padding: 12px 10px; color: #475569;">${product.nr_receptury || '<span style="color: #cbd5e1;">-</span>'}</td>
            <td style="padding: 12px 10px; color: #475569;">${typDisplay}</td>
            <td style="padding: 12px 10px; font-size: 13px; color: #475569;">
              <div style="display: flex; flex-direction: column; gap: 3px;">
                <div style="display: flex; align-items: center; gap: 4px;">
                  <span style="color: #64748b; font-weight: 500;">Worek:</span> 
                  <span style="color: #334155;">${opakowanie}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 4px;">
                  <span style="color: #64748b; font-weight: 500;">Etykieta:</span> 
                  <span style="color: #334155; display: inline-flex; align-items: center; gap: 6px;">${etykieta} ${etykietaBadge}</span>
                </div>
              </div>
            </td>
            <td style="padding: 12px 10px; text-align: right;">
              <div style="display: flex; gap: 6px; justify-content: flex-end;">
                <button class="btn-icon-small btn-icon-edit" data-id="${product.id}" onclick="editProduct(${product.id})" style="padding: 6px 12px; font-size: 12px;">✏️ Edit</button>
                <button class="btn-icon-small btn-icon-delete" data-id="${product.id}" onclick="deleteProduct(${product.id})" style="padding: 6px 12px; font-size: 12px;">🗑️ Delete</button>
              </div>
            </td>
          </tr>
        `;
      });

      html += `
          </tbody>
        </table>
      `;

      productsList.innerHTML = html;

      // Add hover effect
      productsList.querySelectorAll('.product-table-row').forEach(row => {
        row.style.cursor = 'pointer';
        row.addEventListener('mouseover', () => { row.style.backgroundColor = '#f8fafc'; });
        row.addEventListener('mouseout', () => { row.style.backgroundColor = 'transparent'; });
      });
    };

    window.editProduct = (id) => {
      const product = produktyList.find(p => p.id === id);
      if (!product) return;

      openProductModal(product);
    };

    window.deleteProduct = (id) => {
      var doDelete = () => {
        fetch(`/api/produkty/${id}`, {
          method: 'DELETE'
        })
          .then(r => r.json())
          .then(data => {
            if (data.success) {
                  safeAlert('Sukces', 'Produkt usunięty');
              loadProdukty(() => {
                loadProductsForManagement();
              });
            } else {
                  safeAlert('Błąd', data.message || 'Błąd');
            }
          })
          .catch(e => {
            console.error(e);
                safeAlert('Błąd sieci', 'Błąd sieci');
          });
      };
      
      if (typeof safeConfirm === 'function') {
        safeConfirm('Czy na pewno chcesz usunąć ten produkt?', doDelete);
      } else {
        if (confirm('Czy na pewno chcesz usunąć ten produkt?')) doDelete();
      }
    };

    // Open/close management modal
    btnManageProducts.addEventListener('click', () => {
      const searchInp = document.getElementById('manageSearchInput');
      if (searchInp) {
        searchInp.value = '';
      }
      manageModalBackdrop.classList.add('active');
      manageModal.classList.add('active');
      loadProductsForManagement();
    });

    const btnCloseManageModal = document.getElementById('btnCloseManageModal');
    if (btnCloseManageModal) {
      btnCloseManageModal.addEventListener('click', () => {
        manageModalBackdrop.classList.remove('active');
        manageModal.classList.remove('active');
      });
    }

    const manageSearchInput = document.getElementById('manageSearchInput');
    if (manageSearchInput) {
      manageSearchInput.addEventListener('input', loadProductsForManagement);
    }

    manageModalBackdrop.addEventListener('click', () => {
      manageModalBackdrop.classList.remove('active');
      manageModal.classList.remove('active');
    });

    // Planning info modal event listeners
    if (btnOpenPlanningInfo) {
      btnOpenPlanningInfo.addEventListener('click', () => {
        if (infoModalBackdrop && infoModal) {
          infoModalBackdrop.classList.add('active');
          infoModal.classList.add('active');
        }
      });
    }

    const closeInfoModal = () => {
      if (infoModalBackdrop && infoModal) {
        infoModalBackdrop.classList.remove('active');
        infoModal.classList.remove('active');
      }
    };

    if (btnDismissInfo) {
      btnDismissInfo.addEventListener('click', () => {
        localStorage.setItem(storageKey, 'true');
        closeInfoModal();
        if (planningInfoBanner) {
          planningInfoBanner.style.transition = 'all 0.3s ease';
          planningInfoBanner.style.opacity = '0';
          planningInfoBanner.style.transform = 'translateY(-10px)';
          setTimeout(() => {
            planningInfoBanner.style.display = 'none';
          }, 300);
        }
      });
    }

    if (infoModalBackdrop) {
      infoModalBackdrop.addEventListener('click', closeInfoModal);
    }

    checkInfoBanner();

    loadProdukty();

    updateTableVisibility();
  })();
