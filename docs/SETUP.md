# Setup — from zero to hands-off, without paying

Time: about 2 hours. Cost: $0 (every service below stays inside a free tier or the hackathon
allocation). Steps marked **(you)** need your accounts; everything else is in the repo.

## 0. Accounts **(you)**

1. Register on Devpost and complete the **GitLab Transcend contributor onboarding** (≈24 h approval):
   you get a group in the hackathon namespace with GitLab Duo Agent Platform enabled.
2. Google Cloud: create a project. A billing account is required even for the free tier; new accounts
   also get trial credits. Immediately create a **$1 budget alert** (Billing → Budgets & alerts) so
   nothing can surprise you.

## 1. Put the code on GitLab

```bash
git clone <this repo> joule-thief && cd joule-thief
git remote add gitlab git@gitlab.com:<hackathon-group>/joule-thief.git
git push gitlab HEAD:main
```

Make the project **public**, keep `LICENSE` (MIT) at the root so it shows in the About section.

## 2. Local check (optional)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --reload       # http://localhost:8000
```

## 3. Google Cloud, keyless, with OpenTofu/Terraform **(you, once)**

Use the **GitLab-managed state from the first apply**, so CI and your laptop share one state.
In GitLab: Operate → Terraform states → "Copy Terraform init command" for a state named `production`
(it uses a personal access token with `api` scope). Then, authenticated to Google Cloud with
`gcloud auth application-default login`:

```bash
cd infra/terraform
tofu init <paste the backend-config flags from GitLab>
export TF_VAR_project_id=<gcp-project> TF_VAR_gitlab_project_path=<group>/joule-thief
export TF_VAR_tick_key=$(openssl rand -hex 16) TF_VAR_gitlab_token=<project-access-token>
tofu apply
```

Outputs: `service_url`, `wif_provider`, `artifact_registry_repo`. Optional: `TF_VAR_enable_green_runner=true`
and `TF_VAR_runner_token=glrt-...` create an always-free e2-micro runner in Oregon. Create the runner
token in GitLab (Settings → CI/CD → Runners → New project runner) with the tag `green-runner`.

Add the same `TF_VAR_tick_key`, `TF_VAR_gitlab_token` (masked) and `TF_VAR_flow_consumer_id` as CI/CD
variables, so `configure:infra` re-applies the same configuration instead of removing the scheduler.

## 4. CI/CD variables (Settings → CI/CD → Variables)

| Variable | Value | Masked |
|---|---|---|
| `JOULE_GITLAB_TOKEN` | Project access token, role Developer, scope `api` | yes |
| `GCP_PROJECT_ID` | your project id | no |
| `GCP_WIF_PROVIDER` | `wif_provider` output | no |
| `GCP_AR_REPO` | `joule-thief` | no |
| `JOULE_FLOW_CONSUMER_ID` | see step 5 | no |
| `JOULE_CONTROL_ID`, `JOULE_CONTROL_SECRET` | see step 7 (Ultimate) | secret masked |
| `JOULE_MONTHLY_CAP_G` | monthly carbon budget in grams, e.g. `5000` | no |

Protect `main` (Workload Identity only trusts protected refs).

## 5. Duo Agent Platform

1. **AI → Flows → New flow** for each file in `.gitlab/duo/flows/` (paste the YAML; visibility Private).
2. Enable each flow in the project and add its trigger (**AI → Triggers**):

| Flow | Trigger |
|---|---|
| surge-intake | Work item → Created |
| carbon-reviewer | Assign reviewer (a human asks). CI also starts it through the Flows API when an MR regresses joules/request or edits a hot line |
| retry-guard | Pipeline events → Failed |
| surge-worker | none: the dispatcher starts it through the Flows API |

The closing "Shipped" note on delivered issues is written by `joule shipped` in `govern:footprint` (no LLM: it
copies the pipeline's numbers). File deferrable work with the **Surge Request** issue template: it sets the
labels, so triage needs one call.

3. Find the surge-worker consumer id (GraphQL `aiCatalogConfiguredItems`, see the Flows API docs) and
   set `JOULE_FLOW_CONSUMER_ID`. Without it, the dispatcher falls back to the foundational
   `developer/v1` flow. Do the same for carbon-reviewer → `JOULE_REVIEWER_CONSUMER_ID` (without it the MR
   energy note asks a human to assign the reviewer instead).
4. **AI → Agents → New agent** for `.gitlab/duo/agents/grid.md` and `carbon-accountant.md`.
5. Put the Cloud Run URL in `.gitlab/duo/mcp.json` and allow the MCP server in the group's Duo settings.

## 6. The heartbeat

Either Cloud Scheduler (created by Terraform when `tick_key` is set, every 30 min, free) or GitLab
schedules (Build → Pipeline schedules):

| Schedule | Variable | Cron |
|---|---|---|
| Dispatcher | `JOULE_TASK=tick` | `*/30 * * * *` (skip if Cloud Scheduler is on) |
| Daily plan | `JOULE_TASK=plan` | `0 13 * * *` (after European day-ahead publication) |
| Eco-mode | `JOULE_TASK=eco` | `15 * * * *` |

Create the feature flag `eco-mode` (Deploy → Feature flags) and set `JOULE_UNLEASH_URL` /
`JOULE_UNLEASH_INSTANCE_ID` on the Cloud Run service (values shown in the flags page → Configure).

## 7. Governance (Ultimate)

Secure → Compliance center → Frameworks → New framework "Carbon budget" → requirement with an
**external control** (URL: the Cloud Run `/healthz`, HMAC secret: generate one, ping disabled).
Note its id → `JOULE_CONTROL_ID`, secret → `JOULE_CONTROL_SECRET`. `govern:footprint` reports pass/fail.

## 8. Free-tier guardrails

| Service | Free allowance | Joule Thief usage |
|---|---|---|
| Cloud Run | 180k vCPU-s, 360k GiB-s, 2 M requests / month | scale to zero, ~1.5k ticks/month |
| Cloud Scheduler | 3 jobs | 1 job |
| Artifact Registry | 0.5 GB | cleanup keeps 5 images |
| Secret Manager | 6 active versions | 1 |
| Compute Engine | 1 e2-micro in us-west1/us-central1/us-east1 | optional green runner |
| Sigstore, Energy-Charts, NESO, Open-Meteo | free public services | — |
