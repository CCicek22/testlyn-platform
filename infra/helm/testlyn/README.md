# Testlyn Helm Chart

Version: 0.1.0 — GKE Autopilot (also compatible with EKS, AKS, OpenShift via standard K8s objects).

## Prerequisites

- Helm 3.12+
- kubectl configured against target cluster
- Workload Identity Federation configured on GKE (for GCP secret access)
- `testlyn-secrets` Kubernetes Secret pre-populated (see below)

## Install

```bash
# Create namespace
kubectl create namespace testlyn

# Pre-populate secrets (never commit values — pull from Secret Manager)
kubectl create secret generic testlyn-secrets -n testlyn \
  --from-literal=DATABASE_URL="$(gcloud secrets versions access latest --secret=testlyn-db-url)" \
  --from-literal=REDIS_URL="$(gcloud secrets versions access latest --secret=testlyn-redis-url)" \
  --from-literal=STRIPE_SECRET_KEY="$(gcloud secrets versions access latest --secret=testlyn-stripe-secret)" \
  --from-literal=STRIPE_WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=testlyn-stripe-webhook-secret)" \
  --from-literal=SENDGRID_API_KEY="$(gcloud secrets versions access latest --secret=testlyn-sendgrid-key)"

# Install chart
helm install testlyn ./infra/helm/testlyn \
  --namespace testlyn \
  --set global.gcpProject=example-project-prod \
  --set licenseKey=YOUR_LICENSE_KEY
```

## Air-gapped install

```bash
# 1. Bundle images on connected machine
bash infra/scripts/bundle-images.sh --license YOUR_LICENSE_KEY --output /tmp/testlyn-bundle.tar.gz

# 2. Transfer bundle to air-gapped environment
scp /tmp/testlyn-bundle.tar.gz airgap-host:/tmp/

# 3. On air-gapped host: load images and push to internal registry
tar xzf /tmp/testlyn-bundle.tar.gz
cat manifest.txt | while read image; do
  docker load < "images/$(echo $image | tr '/:' '_').tar"
  docker tag $image internal-registry.corp/$image
  docker push internal-registry.corp/$image
done

# 4. Install with registry override
helm install testlyn ./infra/helm/testlyn \
  --namespace testlyn \
  --set imageRegistry=internal-registry.corp/testlyn \
  --set licenseKey=YOUR_LICENSE_KEY
```

## Values reference

See `values.yaml` — all keys documented inline.

Key overrides:

| Key | Default | Description |
|-----|---------|-------------|
| `imageRegistry` | GCR path | Override for air-gapped installs |
| `licenseKey` | `""` | Enterprise license key |
| `global.env` | `prod` | Environment label |
| `postgres.bundled` | `false` | Deploy bundled postgres (dev only) |
| `redis.bundled` | `false` | Deploy bundled redis (dev only) |
| `bqEmulator.enabled` | `false` | Deploy BQ emulator (dev/CI only) |
| `api.autoscaling.enabled` | `true` | HPA for API |
| `ingress.enabled` | `true` | Create Ingress resources |

## Upgrading

```bash
helm upgrade testlyn ./infra/helm/testlyn --namespace testlyn --reuse-values
```

## Linting

```bash
helm lint ./infra/helm/testlyn
```
