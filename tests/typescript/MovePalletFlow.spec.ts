
/*
  To jest przykładowy plik testowy dla Playwright.
  Nie będzie działał bezpośrednio w środowisku React bez konfiguracji Playwright,
  ale pokazuje jak testować pełny proces biznesowy.
*/

import { test, expect } from '@playwright/test';

test('User can move a pallet from Buffer to Production', async ({ page }) => {
  // 1. Login
  await page.goto('/');
  await page.fill('#username', 'magazynier');
  await page.fill('#password', 'password');
  await page.click('button:has-text("Zaloguj się")');

  // 2. Go to Scanning Page
  await page.click('text=Skanuj'); 

  // 3. Scan Pallet (Mock ID existing in initialData)
  await page.fill('input[id*="manual-scan"]', 'some-raw-id-1'); 
  await page.click('button:has-text("Zatwierdź")');

  // 4. Verify Pallet Info appears
  await expect(page.locator('text=Zeskanowana Pozycja')).toBeVisible();

  // 5. Scan Target Location (Valid move)
  await page.fill('input[id*="manual-scan"]', 'MP01'); // Assuming target input is reused or cleared
  await page.click('button:has-text("Zatwierdź")');

  // 6. Verify Success Message
  await expect(page.locator('text=Przeniesiono pomyślnie')).toBeVisible();
});

test('User cannot move blocked pallet to Production', async ({ page }) => {
    // ... Login logic ...

    // Scan a known blocked pallet
    await page.fill('input[id*="manual-scan"]', 'BLOCKED-PALLET-ID'); 
    await page.click('button:has-text("Zatwierdź")');

    // Scan production location
    await page.fill('input[id*="manual-scan"]', 'BB01'); 
    await page.click('button:has-text("Zatwierdź")');

    // Verify Error
    await expect(page.locator('text=Błąd')).toBeVisible();
    await expect(page.locator('text=Zablokowana paleta nie może wejść do strefy produkcyjnej')).toBeVisible();
});
