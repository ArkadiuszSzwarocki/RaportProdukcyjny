# Kubernetes deployment

Manifesty w tym katalogu zakładają produkcyjne wdrożenie przez Ingress. Sekrety **nie są przechowywane w repozytorium**.

## Wymagania

- Kubernetes 1.24+
- Ingress NGINX
- cert-manager
- dynamiczny provisioner PVC
- obraz aplikacji dostępny w rejestrze

## 1. Utwórz namespace i sekrety

Najpierw utwórz namespace i wartości niesekretne:

```bash
kubectl apply -f k8s/00-namespace-config.yaml
```

Następnie utwórz `app-secrets` poza repozytorium:

```bash
kubectl -n raportprodukcyjny create secret generic app-secrets \
  --from-literal=SECRET_KEY="$SECRET_KEY" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=DB_USER="$DB_USER" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
  --from-literal=INITIAL_ADMIN_PASSWORD="$INITIAL_ADMIN_PASSWORD" \
  --from-literal=PRINTER_BRIDGE_TOKEN="$PRINTER_BRIDGE_TOKEN"
```

Wymagania:

- `SECRET_KEY`: unikalny losowy sekret, minimum 32 znaki;
- `ENCRYPTION_KEY`: poprawny klucz Fernet;
- `DB_USER`: użytkownik aplikacyjny MySQL;
- `DB_PASSWORD`: hasło wyłącznie użytkownika aplikacyjnego;
- `MYSQL_ROOT_PASSWORD`: **inne** silne hasło administratora MySQL;
- `INITIAL_ADMIN_PASSWORD`: silne, jednorazowe hasło startowe administratora aplikacji;
- `PRINTER_BRIDGE_TOKEN`: długi losowy sekret współdzielony wyłącznie przez aplikację i mostek druku.

W produkcji preferowany jest zewnętrzny system sekretów, np. External Secrets Operator, Sealed Secrets lub natywny secret store dostawcy chmury.

## 2. Konfiguracja

`00-namespace-config.yaml` zawiera wyłącznie wartości niesekretne. Wewnętrzny port MySQL to `3306`.

Aplikacja WWW ma:

- `TRUST_PROXY_HEADERS=true` i ufa jednemu hopowi Ingress;
- `SESSION_COOKIE_SECURE=true` dla HTTPS zakończonego na Ingress;
- `DB_SSL_DISABLED=false`, więc TLS do MySQL nie jest sterowany ustawieniem TLS serwera WWW;
- `ENABLE_BACKGROUND_DAEMONS=false`, aby każdy worker Gunicorn nie uruchamiał osobnych pętli tła.

Osobny Deployment `app-daemons` uruchamia dokładnie jeden proces `scripts/run_daemons.py`.

### Mostek drukowania

Mostek drukowania jest osobną, uwierzytelnioną usługą. `PRINTER_BRIDGE_TOKEN` musi być taki sam po obu stronach. Rzeczywisty `PRINTER_BRIDGE_URL` zależy od środowiska i **nie powinien zawierać konkretnego produkcyjnego IP w publicznym repo**. Ustaw go przez overlay/ConfigMap środowiska, np. prywatną nazwę DNS usługi albo adres bramy w sieci zakładowej.

Jeżeli mostek działa poza klastrem, NetworkPolicy dopuszcza port `3001` tylko do prywatnych zakresów RFC1918. W środowisku produkcyjnym najlepiej zawęzić te zakresy jeszcze bardziej do konkretnego VLAN/subnetu drukarek.

### Repliki i wolumeny

`app-logs-pvc` oraz `app-raporty-pvc` mają obecnie `ReadWriteOnce`. Z tego powodu bazowy manifest uruchamia **jedną replikę** aplikacji WWW i nie zawiera HPA. Próba skalowania 2–5 podów przy RWO może pozostawić część podów w stanie `Pending`, gdy scheduler rozłoży je na różne węzły.

Autoskalowanie można włączyć dopiero po przeniesieniu raportów/logów na storage obsługujący `ReadWriteMany`, obiektowy backend albo po usunięciu współdzielonych mountów z podów WWW.

## 3. Wdrożenie

Manifest celowo zawiera fail-safe placeholder obrazu:

```text
ghcr.io/arkadiuszszwarocki/raportprodukcyjny:sha-REPLACE_WITH_TESTED_COMMIT
```

**Nie wdrażaj tego placeholdera.** Przed `kubectl apply` zamień oba wystąpienia na dokładny obraz, który przeszedł testy, najlepiej digest `@sha256:...` albo tag `sha-<commit>`.

Przykład z `kubectl set image` po zastosowaniu manifestu w kontrolowanym środowisku:

```bash
kubectl -n raportprodukcyjny set image deployment/app app=ghcr.io/arkadiuszszwarocki/raportprodukcyjny@sha256:<DIGEST>
kubectl -n raportprodukcyjny set image deployment/app-daemons daemons=ghcr.io/arkadiuszszwarocki/raportprodukcyjny@sha256:<DIGEST>
```

Przed wdrożeniem ustaw także właściwą domenę w `03-ingress.yaml` i środowiskowy `PRINTER_BRIDGE_URL`.

```bash
kubectl apply -f k8s/01-mysql.yaml
kubectl apply -f k8s/02-app.yaml
kubectl apply -f k8s/03-ingress.yaml
```

Sprawdzenie:

```bash
kubectl get pods,svc,ingress -n raportprodukcyjny
kubectl rollout status deployment/app -n raportprodukcyjny
kubectl rollout status deployment/app-daemons -n raportprodukcyjny
kubectl logs deployment/app -n raportprodukcyjny
kubectl logs deployment/app-daemons -n raportprodukcyjny
```

## Bezpieczeństwo

- aplikacja i MySQL nie mają automatycznie montowanego tokena ServiceAccount;
- aplikacja nie ma RBAC do odczytu Secrets ani ConfigMaps;
- Service aplikacji jest `ClusterIP`; ruch zewnętrzny przechodzi przez Ingress;
- aplikacja działa jako użytkownik nie-root z UID/GID 1000, ma usunięte Linux capabilities i profil `seccomp: RuntimeDefault`;
- NetworkPolicy wpuszcza ruch WWW tylko z namespace `ingress-nginx`;
- egress jest ograniczony do MySQL, DNS i jawnie wymienionych portów integracji;
- porty mostka/RAW printer są ograniczone do prywatnych zakresów sieci;
- sekrety nie są częścią manifestów Git;
- obrazy produkcyjne muszą być wskazane przez niezmienny digest albo konkretny testowany tag, nigdy `latest`.

`readOnlyRootFilesystem` pozostaje wyłączone, ponieważ obecny panel administracyjny zapisuje część konfiguracji do `/app/config`. Włączenie tej opcji wymaga wcześniejszego przeniesienia zapisywalnej konfiguracji do osobnego wolumenu lub bazy danych.

Jeżeli środowisko wymaga innych usług wychodzących, rozszerz NetworkPolicy w środowiskowym overlayu zamiast otwierać cały egress.

## Aktualizacja sekretu

Nie edytuj wartości sekretów w repo. Do rotacji użyj secret store albo:

```bash
kubectl -n raportprodukcyjny create secret generic app-secrets \
  --from-literal=SECRET_KEY="$SECRET_KEY" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=DB_USER="$DB_USER" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
  --from-literal=INITIAL_ADMIN_PASSWORD="$INITIAL_ADMIN_PASSWORD" \
  --from-literal=PRINTER_BRIDGE_TOKEN="$PRINTER_BRIDGE_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Po rotacji sekretów wykonaj kontrolowany restart odpowiednich Deploymentów.