# Deployment

One container image runs everywhere. Pick the target that matches the client's platform; in every case use Postgres for persistence and put the app behind the platform's SSO.

Build:

```bash
docker build -t ai-use-case-atlas .                                       # core
docker build --build-arg EXTRAS="databricks-sdk" -t ai-use-case-atlas .   # + Unity Catalog / Databricks serving
docker build --build-arg EXTRAS="google-cloud-bigquery google-auth" -t ai-use-case-atlas .  # + BigQuery / Vertex
```

The container listens on `$PORT` (default 8000), or `$DATABRICKS_APP_PORT` on Databricks Apps.

## Google Cloud (e.g. Australia Post): Cloud Run + Cloud SQL + Vertex AI + BigQuery

1. Cloud SQL for PostgreSQL instance and database `atlas`; store the URL in Secret Manager as `atlas-db-url`, e.g. `postgresql+psycopg://atlas:<pw>@/atlas?host=/cloudsql/<project>:australia-southeast1:<instance>`.
2. Service account for the app with: `roles/cloudsql.client`, `roles/aiplatform.user` (Vertex), `roles/bigquery.metadataViewer` on datasets in scope and `roles/bigquery.jobUser` on the project, `roles/secretmanager.secretAccessor`.
3. Build with `EXTRAS="google-cloud-bigquery google-auth"` and push to Artifact Registry.
4. Deploy:

```bash
gcloud run deploy ai-use-case-atlas \
  --image australia-southeast1-docker.pkg.dev/<project>/<repo>/ai-use-case-atlas \
  --region australia-southeast1 --service-account atlas@<project>.iam.gserviceaccount.com \
  --add-cloudsql-instances <project>:australia-southeast1:<instance> \
  --set-secrets DATABASE_URL=atlas-db-url:latest \
  --set-env-vars FRAMEWORK=auspost,LLM_PROVIDER=vertex,VERTEX_PROJECT=<project>,VERTEX_REGION=<region>,LLM_MODEL=<vertex model id>,CATALOG_ADAPTER=bigquery,BQ_PROJECT=<project>,BQ_REGION=australia-southeast1,SEED_DEMO_DATA=false \
  --no-allow-unauthenticated
```

5. Put Identity-Aware Proxy (IAP) in front, so users sign in with corporate identity; the app reads `X-Goog-Authenticated-User-Email`.

Check: Claude model availability and data residency on Vertex AI vary by region. Confirm the region and model ID against the client's data handling requirements before go-live.

## Databricks (e.g. Deakin): Databricks Apps + Lakebase + Model Serving + Unity Catalog

1. Create a Lakebase (Postgres) database, or use an existing Azure Database for PostgreSQL, and store its URL as a secret.
2. Create the app from this repository. `app.yaml` is the manifest; add app resources:
   - `serving-endpoint`: the model serving endpoint (CAN QUERY)
   - `sql-warehouse`: a SQL warehouse (CAN USE)
   - `atlas-db-url`: secret with the Postgres URL
3. Grant the app's service principal `USE CATALOG`, `USE SCHEMA` and `BROWSE` on catalogues in scope (`UC_CATALOGS`). It reads `system.information_schema` only.
4. Install `databricks-sdk` (add it to `requirements.txt` for the app, since Databricks Apps installs from that file).
5. Users sign in through the workspace; the app reads `X-Forwarded-Email`.

`LLM_PROVIDER=databricks` uses the SDK's OpenAI client with the app's own service principal, so no tokens are stored.

## Azure without Databricks: Container Apps + Azure Database for PostgreSQL

- Deploy the image to Azure Container Apps with ingress on port 8000 and Easy Auth (Entra ID) enabled; the app reads `X-MS-CLIENT-PRINCIPAL-NAME`.
- `LLM_PROVIDER=openai_compatible` with `OPENAI_BASE_URL` set to the Azure OpenAI v1 endpoint, or `anthropic` if Claude is approved.
- Store `DATABASE_URL` and API keys in Key Vault-backed secrets.

## Workshop laptop (no infrastructure)

`uvicorn app.main:app --port 8000` with SQLite. Export the backlog and portfolio pack at the end of the session. Do not use SQLite for a shared deployment.

## Operational notes

- Back up the Postgres database; it is the system of record for the backlog and audit trail.
- `GET /healthz` for liveness probes.
- Set `SEED_DEMO_DATA=false` in client environments.
