#!/usr/bin/env bash
# One-time move of a Helm release's records from Secrets (Helm's default driver) to ConfigMaps
# (HELM_DRIVER=configmap), so a deploy identity without `secrets` verbs keeps the release history
# and upgrades instead of re-installing (ADR-035 amendment 1). Run with an ADMIN kubeconfig:
#
#   make helm-driver-migrate KUBECONFIG=<admin kubeconfig> [DELETE_SECRETS=1]
#
# Copies every `sh.helm.release.v1.<release>.vN` Secret to a ConfigMap of the same name, labels
# and decoded payload (the Secret driver base64-encodes Helm's release string once more; the
# ConfigMap driver stores it as is), then checks that `helm history` under the ConfigMap driver
# lists every revision the Secrets hold. Only then, and only with DELETE_SECRETS=1, the Secrets are deleted.
set -euo pipefail

NAMESPACE="${NAMESPACE:?NAMESPACE unset}"
RELEASE="${RELEASE:?RELEASE unset}"
KUBECTL="${KUBECTL:-kubectl}"
HELM="${HELM:-helm}"

k() { "${KUBECTL}" -n "${NAMESPACE}" "$@"; }

secrets="$(k get secret -l "owner=helm,name=${RELEASE}" -o name)"
if [ -z "${secrets}" ]; then
  echo "helm-driver-migrate: no Secret-stored records for ${RELEASE} in ${NAMESPACE} (nothing to do)"
  exit 0
fi

for s in ${secrets}; do
  name="${s#secret/}"
  if k get configmap "${name}" >/dev/null 2>&1; then
    echo "helm-driver-migrate: configmap/${name} exists, kept"
    continue
  fi
  k get "${s}" -o json | python3 -c '
import base64, json, sys
s = json.load(sys.stdin)
meta = s["metadata"]
print(json.dumps({
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": meta["name"], "namespace": meta["namespace"], "labels": meta["labels"]},
    "data": {"release": base64.b64decode(s["data"]["release"]).decode("ascii")},
}))' | k create -f - >/dev/null
  echo "helm-driver-migrate: ${s} → configmap/${name}"
done

want="$(k get secret -l "owner=helm,name=${RELEASE}" -o jsonpath='{range .items[*]}{.metadata.labels.version}{"\n"}{end}' | sort -n | tr '\n' ' ')"
got="$(HELM_DRIVER=configmap "${HELM}" -n "${NAMESPACE}" history "${RELEASE}" -o json \
  | python3 -c 'import json,sys; print(" ".join(str(r["revision"]) for r in sorted(json.load(sys.stdin), key=lambda r: r["revision"])))')"
for rev in ${want}; do
  case " ${got} " in
    *" ${rev} "*) ;;
    *) echo "helm-driver-migrate: FAIL — Secret revision ${rev} is not in the ConfigMap history [${got}]; Secrets kept"; exit 1;;
  esac
done
echo "helm-driver-migrate: HELM_DRIVER=configmap history = revisions ${got}"

if [ "${DELETE_SECRETS:-}" = "1" ]; then
  k delete ${secrets} >/dev/null
  echo "helm-driver-migrate: Secret-stored records deleted"
else
  echo "helm-driver-migrate: Secret-stored records kept (DELETE_SECRETS=1 removes them)"
fi
