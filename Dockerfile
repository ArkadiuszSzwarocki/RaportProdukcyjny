# Używamy lekkiej wersji Node.js 18
FROM node:18-alpine

# Ustawiamy folder roboczy w kontenerze
WORKDIR /app

# Kopiujemy pliki konfiguracyjne (zależności)
COPY package*.json ./

# Instalujemy WSZYSTKIE zależności (również te deweloperskie, bo są potrzebne do Vite i concurrently)
RUN npm install --legacy-peer-deps

# Kopiujemy resztę kodu aplikacji
COPY . .

# Ensure version file (generated in CI) is copied into image public folder
COPY public/version.txt public/version.txt

# Otwieramy porty.
# 5173 - domyślny port Vite (Frontend)
# 8089 - częsty port dla server.js (Backend) - jeśli masz inny, zmienimy to
EXPOSE 5173
EXPOSE 8089

# Komenda startowa - uruchamia to samo co u Ciebie lokalnie (front i back razem)
CMD ["npm", "run", "dev"]
