# Zrzuty ekranu w zgłoszeniach

Baza przechowuje nazwy plików w `zgloszenia_bledow.zalaczniki`; same obrazy znajdują się w `static/uploads/bugs`. Podłączenie lokalnej aplikacji do bazy na QNAP nie kopiuje obrazów.

Miniatury administratora, powiększenie i „Moje zgłoszenia” używają jednego endpointu `/admin/zalaczniki/<filename>` i jednego resolvera. Opcjonalne `BUG_ATTACHMENTS_DIR` może wskazywać udostępniony lub skopiowany katalog załączników. Resolver najpierw sprawdza ten katalog, potem dawny `static/uploads/bugs`. Brak pliku jest pokazywany jawnie; nie tworzymy pozornego obrazu zastępczego.

Nowe zgłoszenie z załącznikiem nie jest zapisywane jako pomyślne, jeżeli nie udało się zapisać obrazu. Konfiguracje Compose zawierają nazwany wolumen `bug_attachments` dla katalogu obrazów. Zmiany przygotowano lokalnie; nie wdrożono ich na QNAP.

Przed pierwszym wdrożeniem wolumenu należy zachować pliki z aktualnego kontenera lub kopii zapasowej i przenieść je do nowego magazynu. Nie odtwarzać kontenera przed zachowaniem tych plików. Samo utworzenie wolumenu nie odzyska plików z poprzednich kontenerów.

Aby obejrzeć historyczne obrazy lokalnie, należy skopiować ich oryginalne pliki do `static/uploads/bugs` lub wskazać katalog przez `BUG_ATTACHMENTS_DIR`. Istniejących nazw w bazie nie zmieniamy.
