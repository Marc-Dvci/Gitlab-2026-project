#!/bin/sh
# Exchange this job's GitLab OIDC token for a short-lived Google Cloud access token
# (Workload Identity Federation): no service-account keys anywhere, nothing to rotate, $0.
# Needs: GITLAB_OIDC_TOKEN (id_tokens, aud https://gitlab.com), GCP_WIF_PROVIDER
# (projects/<number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>).
# Optional: GCP_DEPLOYER_SA to impersonate a service account instead of direct federation.
set -eu
: "${GITLAB_OIDC_TOKEN:?missing id_tokens GITLAB_OIDC_TOKEN}" "${GCP_WIF_PROVIDER:?set GCP_WIF_PROVIDER}"
federated=$(curl -sS --fail https://sts.googleapis.com/v1/token \
  -d grant_type=urn:ietf:params:oauth:grant-type:token-exchange \
  -d audience="//iam.googleapis.com/${GCP_WIF_PROVIDER}" \
  -d scope=https://www.googleapis.com/auth/cloud-platform \
  -d requested_token_type=urn:ietf:params:oauth:token-type:access_token \
  -d subject_token_type=urn:ietf:params:oauth:token-type:jwt \
  -d subject_token="${GITLAB_OIDC_TOKEN}" | tr -d '\n ' | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [ -n "${GCP_DEPLOYER_SA:-}" ]; then
  curl -sS --fail -X POST -H "Authorization: Bearer ${federated}" -H "Content-Type: application/json" \
    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${GCP_DEPLOYER_SA}:generateAccessToken" \
    -d '{"scope":["https://www.googleapis.com/auth/cloud-platform"]}' | tr -d '\n ' | sed -n 's/.*"accessToken":"\([^"]*\)".*/\1/p'
else
  printf '%s' "${federated}"
fi
