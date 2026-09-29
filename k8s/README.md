# Kubernetes deployment

Manifesty w tym katalogu zakładają produkcyjne wdrożenie przez Ingress. Sekrety **nie są przechowywane w repozytorium**.

## Wymagania

- Kubernetes 1.24+
- Ingress NGINX
- cert-manager
- dynamiczny provisioner PVC
- obraz aplikacji dostępny w rejestrze

## 1. Utwórz namespace i sekrety

Najpierw utwórz namespace:

```bash
kubectl apply -f k8s/00-namespace-config.yaml
```

Następnie utwórz `app-secrets` poza repozytorium. Przykład z lokalnych zmiennych środowiskowych:

```bash
kubectl -n raportprodukcyjny create secret generic app-secrets \
  --from-literal=SECRET_KEY="$SECRET_KEY" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=DB_USER="$DB_USER" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
  --from-literal=INITIAL_ADMIN_PASSWORD="$INITIAL_ADMIN_PASSWORD"
```

Wymagania:

- `SECRET_KEY`: unikalny losowy sekret, minimum 32 znaki;
- `ENCRYPTION_KEY`: poprawny klucz Fernet;
- `DB_USER`: użytkownik aplikacyjny MySQL;
- `DB_PASSWORD`: hasło wyłącznie użytkownika aplikacyjnego;
- `MYSQL_ROOT_PASSWORD`: inne, silne hasło administratora MySQL;
- `INITIAL_ADMIN_PASSWORD`: silne hasło startowe administratora aplikacji.

W produkcji preferowany jest zewnętrzny system sekretów, np. External Secrets Operator, Sealed Secrets lub natywny secret store dostawcy chmury.

## 2. Konfiguracja

`00-namespace-config.yaml` zawiera wyłącznie wartości niesekretne. Wewnętrzny port MySQL to `3306`.

Aplikacja WWW ma:

- `TRUST_PROXY_HEADERS=true` i ufa jednemu hopowi Ingress;
- `ENABLE_BACKGROUND_DAEMONS=false`, aby każdy worker Gunicorn nie uruchamiał osobnych pętli tła.

Osobny Deployment `app-daemons` uruchamia dokładnie jeden proces `scripts/run_daemons.py`.

## 3. Wdrożenie

Przed wdrożeniem ustaw właściwą domenę w `03-ingress.yaml` oraz używany obraz aplikacji. W środowisku produkcyjnym zalecane jest przypięcie obrazu po digest zamiast korzystania z mutable tagu.

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
- aplikacja działa jako użytkownik nie-root i ma usunięte Linux capabilities;
- NetworkPolicy wpuszcza ruch WWW tylko z namespace `ingress-nginx`;
- egress jest ograniczony do MySQL, DNS oraz jawnie wymienionych portów integracji;
- sekrety nie są częścią manifestów Git.

Jeżeli środowisko wymaga innych usług wychodzących (np. niestandardowego portu MQTT, SMTP lub mostka drukowania), należy rozszerzyć NetworkPolicy w środowiskowym overlayu zamiast otwierać cały ruch.

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
  --dry-run=client -o yaml | kubectl apply -f -
```

Po rotacji sekretów wykonaj kontrolowany restart odpowiednich Deploymentów.
