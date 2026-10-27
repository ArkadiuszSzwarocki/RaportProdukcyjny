<!-- cspell:words wydozowan wydozowań -->
# Czasy etapów Zasypu

Raport znajduje się w Raporty → Czasy wydozowań i etapów (`/raporty/czasy-wydozowan`). Jest także dostępny z raportów okresowych. Obowiązują uprawnienia strony wyników.

Filtry: zakres dat do 366 dni, hala AGRO / PSD / obie i konkretne zlecenie rozpoznawane po hali oraz numerze. Zakres wybiera zlecenia według daty planu (oba dni graniczne włącznie), a następnie pokazuje cały ich przebieg. Zlecenie jest rozwijane na szarże i etapy. Sekwencja procesu zachowuje powtarzane dosypki; osobna kolumna pokazuje rzeczywistą kolejność zapisanych START.

Raport korzysta wyłącznie z istniejącej tabeli `zasyp_etapy`. Nie tworzy ani nie naprawia tabel i nie zmienia zapisów produkcyjnych. Brakujące czasy pozostają nieznane. Brutto oznacza odcinek od START do STOP; dla trwających etapów do chwili wygenerowania raportu. Praca to brutto minus zapisane pauzy i aktualna trwająca pauza. Błędne daty lub pauzy powodują oznaczenie braku poprawnego pomiaru. Nakładające się etapy mogą mieć sumę czasów większą niż czas zegarowy szarży.

To raport etapów obsługi procesu, nie pomiar otwarcia zaworów poszczególnych surowców. Dostępne są dwa wykresy, szczegółowe tabele, drukowanie i CSV z pełnymi czasami w sekundach.
