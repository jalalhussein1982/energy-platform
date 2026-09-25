#!/usr/bin/env bash
# Alert delivery drill (ADR-040; review 3 R3) on the local kind cluster.
#
#   make alert-drill          (after make local-up)
#
# A controlled failure: a Job named like the restore drill whose one container exits 1. The
# chain is kube-state-metrics (kube_job_status_failed) → Prometheus (EnergyPlatformRestoreDrillFailed,
# for: 1m) → Alertmanager (group_wait 10s) → the platform receiver's webhook. The drill waits for
# a `firing` delivery naming the alert in the receiver's log, deletes the Job, then waits for the
# `resolved` delivery. Exit 1 unless both arrived. Nothing else is touched: no capture, no
# schedule, no data. The same steps are the author's on the demo (Level 3).
set -uo pipefail

CTX="${KIND_CONTEXT:-kind-energy-platform}"
NS="${NAMESPACE:-energy-platform}"
RELEASE="${RELEASE:-energy-platform}"
KUBE="${KUBECTL:-kubectl} --context ${CTX} -n ${NS}"
JOB="${RELEASE}-restore-drill-manual-fail"
ALERT="EnergyPlatformRestoreDrillFailed"
FIRE_TIMEOUT="${ALERT_DRILL_FIRE_TIMEOUT:-420}"
RESOLVE_TIMEOUT="${ALERT_DRILL_RESOLVE_TIMEOUT:-420}"
fail=0

pass() { echo "PASS $*"; }
flunk() { echo "FAIL $*"; fail=1; }

sink_pod() { ${KUBE} get pods -l energy-platform.io/role=alert-sink -o jsonpath='{.items[0].metadata.name}' 2>/dev/null; }
deliveries() { ${KUBE} logs "$(sink_pod)" --since-time="$1" 2>/dev/null | grep "\"alertname\": \"${ALERT}\"" || true; }
wait_for() { # $1 status, $2 since, $3 timeout seconds
  local waited=0
  while [ "$waited" -lt "$3" ]; do
    if deliveries "$2" | grep -q "\"status\": \"$1\""; then return 0; fi
    sleep 10; waited=$((waited + 10))
  done
  return 1
}

image="$(${KUBE} get cronjob "${RELEASE}-gaps" -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}')"
[ -n "$image" ] || { echo "alert-drill: cannot read the platform image from the gaps CronJob"; exit 1; }
pull_secrets="$(${KUBE} get cronjob "${RELEASE}-gaps" -o jsonpath='{.spec.jobTemplate.spec.template.spec.imagePullSecrets}')"
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "== alert-drill: receiver pod $(sink_pod), evaluator chain kube-state-metrics → Prometheus → Alertmanager → webhook; since ${since}"

# every component ready before the clock starts
for role in prometheus alertmanager kube-state-metrics alert-sink; do
  if ${KUBE} wait --for=condition=available "deployment/${RELEASE}-${role}" --timeout=180s >/dev/null 2>&1; then pass "${role} available"; else flunk "${role} not available"; fi
done
[ "$fail" -eq 0 ] || exit 1

${KUBE} delete job "${JOB}" --ignore-not-found --wait=true >/dev/null
cat <<YAML | ${KUBE} apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB}
  labels:
    energy-platform.io/test: alert-drill
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 120
  template:
    metadata:
      labels:
        energy-platform.io/test: alert-drill
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      imagePullSecrets: ${pull_secrets:-[]}
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: fail
          image: ${image}
          command: ["/bin/sh", "-c", "echo 'alert-drill: a restore drill that fails on purpose'; exit 1"]
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: ["ALL"]}
          resources:
            requests: {cpu: 10m, memory: 16Mi}
            limits: {cpu: 100m, memory: 64Mi}
YAML
echo "== alert-drill: Job ${JOB} created (exits 1); waiting up to ${FIRE_TIMEOUT}s for a firing delivery"
if wait_for firing "$since" "$FIRE_TIMEOUT"; then
  pass "firing delivered: $(deliveries "$since" | grep '"status": "firing"' | tail -1 | cut -c1-200)…"
else
  flunk "no firing delivery of ${ALERT} within ${FIRE_TIMEOUT}s"
  echo "-- receiver log since ${since}:"; ${KUBE} logs "$(sink_pod)" --since-time="$since" | tail -20
  echo "-- Prometheus alerts:"; ${KUBE} exec "deploy/${RELEASE}-prometheus" -- wget -qO- http://127.0.0.1:9090/api/v1/alerts 2>/dev/null | cut -c1-600
fi

resolved_since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
${KUBE} delete job "${JOB}" --wait=true >/dev/null
echo "== alert-drill: Job deleted; waiting up to ${RESOLVE_TIMEOUT}s for a resolved delivery"
if wait_for resolved "$resolved_since" "$RESOLVE_TIMEOUT"; then
  pass "resolved delivered: $(deliveries "$resolved_since" | grep '"status": "resolved"' | tail -1 | cut -c1-200)…"
else
  flunk "no resolved delivery of ${ALERT} within ${RESOLVE_TIMEOUT}s"
  echo "-- receiver log since ${resolved_since}:"; ${KUBE} logs "$(sink_pod)" --since-time="$resolved_since" | tail -20
fi

if [ "$fail" -eq 0 ]; then echo "== alert-drill: PASS (firing and resolved both delivered to the platform receiver)"; else echo "== alert-drill: FAIL"; fi
exit "$fail"
