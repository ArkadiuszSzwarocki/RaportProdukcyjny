# Używamy lekkiej wersji Pythona na Linuxie
FROM python:3.11-slim

# Ustawiamy katalog roboczy wewnątrz kontenera
WORKDIR /app

# Kopiujemy plik z wymaganiami i instalujemy biblioteki
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalujemy python-dotenv (bo mogło go nie być w requirements)
RUN pip install python-dotenv

# Kopiujemy resztę plików aplikacji do kontenera
COPY . .

# Otwieramy port 8080 (na takim działa waitress w app.py)
EXPOSE 8080

# Ustawiamy strefę czasową na Polskę (ważne dla raportów!)
ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Komenda startowa: uruchom aplikację
CMD ["python", "app.py"]