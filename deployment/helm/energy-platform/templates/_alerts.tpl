{{/*
ADR-037 §4 alert rules, one definition shipped two ways: a plain ConfigMap for any scraper and
a PrometheusRule behind metrics.operator.enabled. Durations assume a 15-minute cadence; the
SLO per target is its cadence (ADR-012).
*/}}
{{- define "energy-platform.alertRules" -}}
groups:
  - name: energy-platform-freshness
    rules:
      - alert: EnergyPlatformTargetLate
        expr: energy_platform_freshness_status_active{status="late"} == 1
        for: 30m
        labels:
          severity: page
        annotations:
          summary: "{{ "{{" }} $labels.target {{ "}}" }} is late: expected publication passed and the partition is not complete (01 §5)"
      - alert: EnergyPlatformPipelineFailed
        expr: energy_platform_pipeline_failed == 1
        for: 15m
        labels:
          severity: page
        annotations:
          summary: "{{ "{{" }} $labels.target {{ "}}" }}: the newest attempt failed after Bronze — our incident (ADR-012)"
      - alert: EnergyPlatformSourceUnavailable
        expr: energy_platform_source_unavailable == 1
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "{{ "{{" }} $labels.target {{ "}}" }}: the source is unreachable for an hour — the source's incident, not ours (ADR-012)"
      - alert: EnergyPlatformFreshnessStale
        expr: energy_platform_freshness_computed_age_seconds > 2700
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "{{ "{{" }} $labels.target {{ "}}" }}: no freshness row for 45 minutes — the gap detector itself stopped"
      - alert: EnergyPlatformExporterDown
        expr: absent(energy_platform_freshness_computed_age_seconds)
        for: 15m
        labels:
          severity: page
        annotations:
          summary: "no freshness metrics at all: exporter, database or scrape path down"
      - alert: EnergyPlatformReconciliationMismatch
        expr: energy_platform_quality_events_last_hour{kind="reconciliation_mismatch"} > 0
        for: 15m
        labels:
          severity: page
        annotations:
          summary: "{{ "{{" }} $labels.target {{ "}}" }}: the two OTE transports disagree on a shared metric — one of them holds wrong data (01 §3; 2026-09-23 a backfill stored another day's file and 9 544 of these went unseen)"
      - alert: EnergyPlatformRestoreDrillFailed
        expr: kube_job_status_failed{job_name=~".*restore-drill.*"} > 0
        for: 1m
        labels:
          severity: page
        annotations:
          summary: "a backup could not be restored or the rebuild from Bronze differs from live (ADR-002; needs kube-state-metrics)"
      - alert: EnergyPlatformReplicationFailed
        expr: kube_job_status_failed{job_name=~".*replicate.*"} > 0
        for: 1m
        labels:
          severity: page
        annotations:
          summary: "Bronze A → B replication reported differences or failed (ADR-036 §3; needs kube-state-metrics)"
      # ADR-036 amendment 2: the RPO for a store-A loss is the replication interval — a job that
      # never runs has no failed-Job metric, so the age of the last success is watched too
      - alert: EnergyPlatformReplicationStale
        expr: time() - max(kube_cronjob_status_last_successful_time{cronjob=~".*-replicate"}) > {{ .Values.bronze.replica.staleAfterSeconds }}
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "no successful Bronze A → B replication for {{ .Values.bronze.replica.staleAfterSeconds }} s: the independent copy is older than the RPO (ADR-036 amendment 2; needs kube-state-metrics)"
      - alert: EnergyPlatformWalShipmentStale
        expr: time() - max(kube_cronjob_status_last_successful_time{cronjob=~".*-pg-wal-ship"}) > {{ .Values.postgres.backup.walStaleAfterSeconds }}
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "no successful WAL shipment for {{ .Values.postgres.backup.walStaleAfterSeconds }} s: Silver RPO exceeded while ingestion may look healthy (ADR-036 amendment 2; needs kube-state-metrics)"
      - alert: EnergyPlatformBaseBackupStale
        expr: time() - max(kube_cronjob_status_last_successful_time{cronjob=~".*-pg-backup"}) > {{ .Values.postgres.backup.baseStaleAfterSeconds }}
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "no successful base backup for {{ .Values.postgres.backup.baseStaleAfterSeconds }} s: the restore replays a longer WAL chain (ADR-036 amendment 2; needs kube-state-metrics)"
{{- end -}}
