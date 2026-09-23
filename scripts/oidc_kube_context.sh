#!/usr/bin/env bash
# Build a kubeconfig from a GitHub Actions ID token (ADR-015 federation clause; V-14; ADR-035 §2).
#
#   scripts/oidc_kube_context.sh <out-file>
#
# Needs, from the workflow: ACTIONS_ID_TOKEN_REQUEST_URL / _TOKEN (permissions: id-token: write)
# and the repository variables DEMO_CLUSTER_URL (https://<ip>:6443) and DEMO_CLUSTER_CA (the
# cluster CA certificate, PEM). No long-lived credential exists anywhere: the token is minted
# for this job (audience energy-platform-demo), the API server maps it to gha:<owner>/<repo>
# and the namespace Role bounds what it may do. Nothing here is a secret; both variables are
# public values (V-14).
set -euo pipefail

OUT="${1:?usage: oidc_kube_context.sh <out-file>}"
AUDIENCE="${OIDC_AUDIENCE:-energy-platform-demo}"
NAMESPACE="${DEMO_NAMESPACE:-energy-platform}"

: "${DEMO_CLUSTER_URL:?DEMO_CLUSTER_URL unset (repository variable: https://<server>:6443)}"
: "${DEMO_CLUSTER_CA:?DEMO_CLUSTER_CA unset (repository variable: the cluster CA, PEM)}"
: "${ACTIONS_ID_TOKEN_REQUEST_URL:?not running under GitHub Actions with id-token: write}"
: "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:?not running under GitHub Actions with id-token: write}"

TOKEN="$(curl -sSf -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${AUDIENCE}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')"

# the claims the API server's validation rules check (claims are public; the token is not printed)
printf '%s' "${TOKEN}" | python3 -c '
import base64, json, sys
payload = sys.stdin.read().split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
print("oidc_kube_context: claims " + json.dumps({k: claims.get(k) for k in ("repository", "ref", "job_workflow_ref", "event_name")}))'

umask 077
CA_FILE="$(mktemp)"
printf '%s\n' "${DEMO_CLUSTER_CA}" > "${CA_FILE}"

kubectl config --kubeconfig="${OUT}" set-cluster demo --server="${DEMO_CLUSTER_URL}" --certificate-authority="${CA_FILE}" --embed-certs=true >/dev/null
kubectl config --kubeconfig="${OUT}" set-credentials gha --token="${TOKEN}" >/dev/null
kubectl config --kubeconfig="${OUT}" set-context demo --cluster=demo --user=gha --namespace="${NAMESPACE}" >/dev/null
kubectl config --kubeconfig="${OUT}" use-context demo >/dev/null
rm -f "${CA_FILE}"

echo "oidc_kube_context: $(kubectl --kubeconfig="${OUT}" auth whoami -o jsonpath='{.status.userInfo.username}' 2>/dev/null || echo 'identity check skipped') → ${OUT}"
