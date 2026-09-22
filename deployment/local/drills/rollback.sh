#!/usr/bin/env bash
# Rollback drill (ADR-016 §6, ADR-025 §5; Phase 5 plan P5-D13) on the local kind cluster.
#
#   make rollback-drill          (after make local-up)
#
# Revision N is the deployed release. Two upgrades are then attempted, each expected to FAIL a
# hook inside `helm upgrade --rollback-on-failure`:
#   (a) smoke.fixture pointed at another target's fixture → the smoke hook cannot produce a
#       Silver row → Helm restores the previous revision;
#   (b) bronze.tiering.mode=lifecycle with storageClass=COLD → the storage-probe hook PUTs
#       with a class the gateway does not implement → Helm restores the previous revision.
# After each: the release is `deployed` with revision N's values, the schema revision is
# unchanged, and the production ledger and Bronze are unchanged (the smoke writes only to a
# throwaway schema and Bronze, P5-D5, so a failed attempt leaves no capture behind — which is
# the point of that design; ADR-025 §5's "captures of the failed attempt present and
# reconciled" is therefore asserted as "production captures untouched").
# Every assertion prints PASS or FAIL; the script exits 1 on any FAIL.
set -uo pipefail

CTX="${KIND_CONTEXT:-kind-energy-platform}"
NS="${NAMESPACE:-energy-platform}"
RELEASE="${RELEASE:-energy-platform}"
HELM="${HELM:-helm} --kube-context ${CTX}"
KUBE="${KUBECTL:-kubectl} --context ${CTX} -n ${NS}"
fail=0

pass() { echo "PASS $*"; }
flunk() { echo "FAIL $*"; fail=1; }
assert_eq() { if [ "$2" = "$3" ]; then pass "$1: $2"; else flunk "$1: got '$2', expected '$3'"; fi; }

values_fixture() { ${HELM} -n "${NS}" get values "${RELEASE}" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("smoke",{}).get("fixture","<default>"))'; }
values_tiering() { ${HELM} -n "${NS}" get values "${RELEASE}" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("bronze",{}).get("tiering",{}).get("mode","<default>"))'; }
release_status() { ${HELM} -n "${NS}" status "${RELEASE}" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["status"])'; }
schema_rev() { ${KUBE} exec "${RELEASE}-postgres-0" -- psql -U energy -d energy -Atc "select version_num from alembic_version"; }
runs_count() { ${KUBE} exec "${RELEASE}-postgres-0" -- psql -U energy -d energy -Atc "select count(*) from runs"; }
obs_count() { ${KUBE} exec "${RELEASE}-postgres-0" -- psql -U energy -d energy -Atc "select count(*) from observations"; }
cronjobs() { ${KUBE} get cronjobs -o name | wc -l | tr -d ' '; }
smoke_schemas() { ${KUBE} exec "${RELEASE}-postgres-0" -- psql -U energy -d energy -Atc "select count(*) from pg_namespace where nspname like 'smoke_%'"; }

# The platform's CronJobs keep capturing live during the drill; a capture landing between the
# baseline and an assertion would make "production unchanged" flaky. Suspend them for the drill
# and always resume them (also on failure or interruption).
resume() { ${KUBE} get cronjobs -o name 2>/dev/null | xargs -r -n1 -I{} ${KUBE} patch {} -p '{"spec":{"suspend":false}}' >/dev/null; echo "== CronJobs resumed"; }
trap resume EXIT
${KUBE} get cronjobs -o name | xargs -r -n1 -I{} ${KUBE} patch {} -p '{"spec":{"suspend":true}}' >/dev/null
${KUBE} wait --for=delete pod -l energy-platform.io/role=capture --timeout=120s >/dev/null 2>&1 || true
echo "== CronJobs suspended for the drill"

echo "== baseline (revision N)"
status0=$(release_status); fixture0=$(values_fixture); tiering0=$(values_tiering)
schema0=$(schema_rev); runs0=$(runs_count); obs0=$(obs_count); cj0=$(cronjobs)
assert_eq "baseline release status" "${status0}" "deployed"
echo "baseline: fixture=${fixture0} tiering=${tiering0} schema=${schema0} runs=${runs0} observations=${obs0} cronjobs=${cj0}"

attempt() {
  local name="$1"; shift
  echo "== attempt ${name}: helm upgrade with $*"
  if make -s deploy-local HELM_EXTRA="$*" >/tmp/ep-drill-"${name}".log 2>&1; then
    flunk "${name}: the upgrade succeeded but was expected to fail its hook"
  else
    pass "${name}: upgrade failed as expected ($(grep -oiE 'hook [^ ]+ failed[^;]*|job [^ ]+ failed[^;]*' /tmp/ep-drill-"${name}".log | head -1))"
  fi
  assert_eq "${name}: release status after rollback" "$(release_status)" "deployed"
  assert_eq "${name}: smoke.fixture restored" "$(values_fixture)" "${fixture0}"
  assert_eq "${name}: tiering.mode restored" "$(values_tiering)" "${tiering0}"
  assert_eq "${name}: schema revision unchanged" "$(schema_rev)" "${schema0}"
  assert_eq "${name}: production runs unchanged" "$(runs_count)" "${runs0}"
  assert_eq "${name}: production observations unchanged" "$(obs_count)" "${obs0}"
  assert_eq "${name}: CronJobs intact" "$(cronjobs)" "${cj0}"
  assert_eq "${name}: no throwaway smoke schema left behind" "$(smoke_schemas)" "0"
}

attempt failing-smoke --set smoke.fixture=ceps_load/fixtures/ordinary_day
attempt failing-storage-probe --set bronze.tiering.mode=lifecycle --set bronze.tiering.storageClass=COLD

echo "== helm history"
${HELM} -n "${NS}" history "${RELEASE}" | tail -6
if [ "${fail}" -eq 0 ]; then echo "rollback-drill: PASS"; else echo "rollback-drill: FAIL"; fi
exit "${fail}"
