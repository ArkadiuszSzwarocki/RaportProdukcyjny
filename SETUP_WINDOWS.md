Instalacja pandas na Windows (zalecane dla świeżego środowiska)
=========================================

Jeśli tworzysz świeże środowisko na Windows, instalacja `pandas` może próbować skompilować pakiet ze źródeł (co często kończy się błędami MSVC). Poniżej są bezpieczne opcje.

Opcja A — użyj Conda (najprostsze, rekomendowane)

1. Zainstaluj Miniconda/Anaconda: https://docs.conda.io/en/latest/miniconda.html
2. Utwórz środowisko (przykład):

```powershell
conda create -n rp python=3.10
conda activate rp
```

3. Zainstaluj zależności (pandas z prebuilt wheel):

```powershell
conda install pandas openpyxl fpdf pymupdf -c conda-forge
```

Opcja B — użyj pip z prebuilt wheel (jeśli dostępny) lub zainstaluj kompatybilną wersję Pythona

1. Jeśli używasz Pythona, dla którego nie ma gotowego wheel (np. najnowsze wydania), rozważ zainstalowanie Pythona 3.10/3.11, gdzie wheel jest dostępny.
2. W wierszu poleceń spróbuj wymusić instalację binarną:

```powershell
# aktywuj swoje venv
python -m pip install --upgrade pip setuptools wheel
python -m pip install pandas --only-binary=:all:
```

3. Jeśli powyższe wyrzuca błąd "no wheels found", użyj conda albo zmień wersję Pythona na jedną z obsługiwanych.

Opcja C — pobranie gotowego wheel ręcznie

1. Przejdź do https://www.lfd.uci.edu/~gohlke/pythonlibs/ (jeśli nadal dostępne) i pobierz wheel dla `pandas` oraz `numpy` zgodny z Twoją wersją Pythona i architekturą.
2. Zainstaluj ręcznie:

```powershell
python -m pip install C:\sciezka\do\numpy‑...whl
python -m pip install C:\sciezka\do\pandas‑...whl
```

Uwagi i wskazówki
- Jeśli planujesz uruchamiać aplikację na produkcji, rozważ użycie `conda` lub obrazu Docker z gotowymi wheelami.
- Dla Windows/MSVC budowanie pandas wymaga narzędzi Meson/Ninja i nagłówków C, co jest trudne; conda eliminuje problem.

Przykładowa sekwencja (szybka, z conda):

```powershell
conda create -n rp python=3.10 -y
conda activate rp
conda install pandas openpyxl fpdf pymupdf -c conda-forge -y
pip install -r requirements.txt  # reszta zależności, jeśli potrzebne
```

Jeśli chcesz, mogę przygotować `environment.yml` dla conda lub dodać alternatywny `requirements-windows.txt` z instrukcjami.
