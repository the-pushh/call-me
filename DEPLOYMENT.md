# Deployment Context — CallMe Backend

This file exists so an AI coding agent (or any new contributor) understands how this repo gets deployed without needing to ask. Read this before making changes that touch environment variables, the Dockerfile, `cloudbuild.yaml`, or anything under `backend/`.

---

## Architecture summary

```
git push origin main (touching backend/**)
   → Cloud Build Trigger fires (call-me-backend-trigger)
      → backend/cloudbuild.yaml runs:
         1. docker build  (backend/Dockerfile)
         2. docker push   → Artifact Registry
         3. gcloud run deploy → Cloud Run (service: callme-api)
            secrets injected from Secret Manager at this step
   → Live at https://api.callme.thepushh.com (via Load Balancer)
```

- **GCP project**: `call-me-voice-agent`
- **Region**: `asia-south1` (Mumbai) — chosen deliberately for low latency to Indian users on the real-time voice pipeline. Do not move regions without reconsidering the Load Balancer setup below.
- **Cloud Run service name**: `callme-api`
- **Artifact Registry repo**: `callme-backend`, image name `callme-api`
- **Trigger config file**: `backend/cloudbuild.yaml`
- **Trigger fires on**: push to `main`, only when files under `backend/**` change (monorepo — root and other folders don't trigger this pipeline)

## Custom domain

`api.callme.thepushh.com` does **not** use Cloud Run's simple domain mapping — `asia-south1` doesn't support that feature (`UNIMPLEMENTED` error if you try `gcloud run domain-mappings create` directly). Instead, there's a full HTTPS Load Balancer in front of Cloud Run:

```
Static IP (callme-api-ip)
   → Forwarding rule (callme-api-https-rule, port 443 only — no HTTP/port 80)
      → Target HTTPS proxy (callme-api-proxy)
         → URL map (callme-api-urlmap)
            → Backend service (callme-api-backend)
               → Serverless NEG (callme-api-neg)
                  → Cloud Run service (callme-api)
```

DNS: an `A` record in Cloudflare (`thepushh.com` zone) — `api.callme` → the static IP, set to **DNS only** (not proxied). SSL is a Google-managed certificate (`callme-api-cert`), separate from Cloud Run's own auto-SSL.

**If this service is ever recreated under a different name**, the entire Load Balancer chain breaks silently (the NEG points at the old service name) and needs to be rebuilt pointing at the new one. Don't rename the Cloud Run service casually.

## Environment variables / secrets

All secrets live in **Secret Manager**, injected into the container as plain environment variables at deploy time via `--set-secrets` in `cloudbuild.yaml`. The app should read them with plain `os.environ[...]` — there is no Secret Manager client code in the app itself, and there shouldn't be.

**Current secrets (names are exact — note the deliberate typo, kept intentionally, do not "fix" it without updating both the secret and every reference):**

| Secret name (Secret Manager) | Used for |
|---|---|
| `FROM_NUMBER` | Twilio outbound caller ID number |
| `OPENROUTER_API_KEY` | LLM calls via OpenRouter |
| `PUBLIC_BASE_URL` | This service's own public URL (`https://api.callme.thepushh.com`) — used for things like Twilio webhook callback URLs |
| `TWILLIO_AUTH_TOKEN` | Twilio auth token — **note the typo, this is intentional, matches the actual secret name** |
| `TWILLIO_SID` | Twilio Account SID — **same typo, same reason** |

**Critical rule:** any code reading these must use the exact spelling above (`TWILLIO_SID`, not `TWILIO_SID`). A mismatch here is a known recurring bug source — it doesn't throw a clear error if accessed via `.get()` with a fallback, it just silently produces empty credentials, which surfaces as a confusing downstream error (e.g. a Twilio 401 "invalid username") rather than an obvious missing-env-var error.

**To check current secret names from the ground truth, not this doc** (in case this doc goes stale):
```bash
gcloud secrets list
```

**To view a secret's current value:**
```bash
gcloud secrets versions access latest --secret=SECRET_NAME
```

**To update a secret's value:**
```bash
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-
```
This alone does **not** redeploy anything — the running container keeps using whatever it already loaded at its last startup. You must trigger a new deploy (see below) for a code/secret change to take effect.

## How to force a redeploy without a code change

Needed when only a secret value changed, with no actual file edit required:

**Option A — GCP Console (simplest):**
Cloud Build → Triggers → find `call-me-backend-trigger` → Run → select branch `main` → Run.

**Option B — empty commit, but it must touch `backend/`:**
An empty commit (`git commit --allow-empty`) touches *zero* files, so it will **not** fire this trigger — the included-files filter (`backend/**`) has nothing to match. Use a real (even trivial) change inside `backend/` instead:
```bash
echo "# redeploy $(date +%s)" >> backend/.redeploy-marker
git add backend/.redeploy-marker
git commit -m "force redeploy"
git push origin main
```

## Port

The app is hardcoded to port `8000` (see `Dockerfile`'s `CMD`). Cloud Run defaults its health check to port `8080` unless told otherwise — `cloudbuild.yaml`'s deploy step explicitly passes `--port=8000` to match. **If you change the app's port, update both** the Dockerfile's `CMD` and the `--port` flag in `cloudbuild.yaml`, or the deploy will fail with a "container failed to start and listen on PORT" error even though the build itself succeeds.

## Service accounts (two separate identities — don't confuse them)

1. **`callme-cloudbuild@call-me-voice-agent.iam.gserviceaccount.com`** — runs the Cloud Build pipeline (build/push/deploy). Has `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`, `logging.logWriter`.
2. **`250047820205-compute@developer.gserviceaccount.com`** (default Compute SA) — what the *live, running* Cloud Run container actually runs as. Has `secretmanager.secretAccessor` granted individually on each of the five secrets above.

If you add a new secret, you must grant accessor permission to identity #2, not #1:
```bash
gcloud secrets add-iam-policy-binding NEW_SECRET_NAME \
  --member="serviceAccount:250047820205-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```
And add it to the `--set-secrets` line in `cloudbuild.yaml`.

## Checking logs

**Build logs** (did the pipeline succeed):
```bash
gcloud builds list --region=global --limit=5
gcloud builds log BUILD_ID --region=global
```

**Application logs** (what the running Python app actually printed/errored):
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=callme-api" \
  --project=call-me-voice-agent --limit=100 --format="value(textPayload)"
```
These are two different things — a successful build does not guarantee the app runs correctly afterward (e.g. port mismatches, env var bugs, runtime crashes all show up only in application logs, not build logs).

## Frontend

Frontend is deployed separately on **Vercel**. It points at this backend through a single environment variable holding `PUBLIC_BASE_URL` (`https://api.callme.thepushh.com`). If this backend's domain ever changes, that Vercel env var needs to be updated to match — they are not automatically synced.

## Full `backend/cloudbuild.yaml` (current, working)

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'asia-south1-docker.pkg.dev/$PROJECT_ID/callme-backend/callme-api:$SHORT_SHA', './backend']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'asia-south1-docker.pkg.dev/$PROJECT_ID/callme-backend/callme-api:$SHORT_SHA']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk:slim'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'callme-api'
      - '--image=asia-south1-docker.pkg.dev/$PROJECT_ID/callme-backend/callme-api:$SHORT_SHA'
      - '--region=asia-south1'
      - '--platform=managed'
      - '--allow-unauthenticated'
      - '--port=8000'
      - '--set-secrets=FROM_NUMBER=FROM_NUMBER:latest,OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest,PUBLIC_BASE_URL=PUBLIC_BASE_URL:latest,TWILLIO_AUTH_TOKEN=TWILLIO_AUTH_TOKEN:latest,TWILLIO_SID=TWILLIO_SID:latest'

images:
  - 'asia-south1-docker.pkg.dev/$PROJECT_ID/callme-backend/callme-api:$SHORT_SHA'

options:
  logging: CLOUD_LOGGING_ONLY
```

## Known gotchas (don't relearn these the hard way)

- `.env` must stay in `.dockerignore` — it's for local dev only, never deployed. Secrets come exclusively from Secret Manager in production.
- Don't trust a green checkmark on GitHub as proof the deploy succeeded — it isn't connected to Cloud Build status. Verify with `gcloud builds list`.
- The included-files filter (`backend/**`) means changes outside `backend/` never trigger a build, including empty commits and root-level file edits.
- A "successful build" only confirms build/push/deploy commands ran — it does not confirm the app started correctly inside the container. Always separately check application logs after a deploy if behavior seems wrong.