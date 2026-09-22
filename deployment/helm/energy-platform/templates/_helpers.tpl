{{/*
energy-platform helpers. Every workload goes through `energy-platform.podSecurity`,
`energy-platform.containerSecurity` and `energy-platform.image` so the restricted-PSS and
digest rules (A-14, ADR-016 §1) are enforced in one place and `make helm-lint` proves it.
*/}}

{{- define "energy-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "energy-platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "energy-platform.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ include "energy-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
energy-platform.io/residency: {{ required "residency is required (ADR-036 §6): CZ | DE | local" .Values.residency | quote }}
{{- end -}}

{{- define "energy-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "energy-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* the platform image, digest only */}}
{{- define "energy-platform.image" -}}
{{- $d := required "image.digest is required (ADR-016 §1): run the deploy Make target, which sets it" .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $d) -}}
{{- fail (printf "image.digest %q is not sha256:<64 hex>" $d) -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository $d -}}
{{- end -}}

{{/* a third-party image from a {repository, digest} block: include "energy-platform.thirdPartyImage" .Values.postgres.image */}}
{{- define "energy-platform.thirdPartyImage" -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" (default "" .digest)) -}}
{{- fail (printf "%s: digest %q is not sha256:<64 hex> (05 C-43)" .repository (default "" .digest)) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- end -}}

{{/* restricted PSS, pod level (ADR-001 amend rule 3). Args: dict "uid" N */}}
{{- define "energy-platform.podSecurity" -}}
runAsNonRoot: true
runAsUser: {{ .uid }}
runAsGroup: {{ .uid }}
fsGroup: {{ .uid }}
fsGroupChangePolicy: OnRootMismatch
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/* restricted PSS, container level */}}
{{- define "energy-platform.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* the S3 environment of P5-D4 for one store: dict "root" $ "prefix" "ENERGY_PLATFORM_S3" "secret" "BRONZE" "store" .Values.bronze */}}
{{- define "energy-platform.s3Env" -}}
- name: {{ .prefix }}_ENDPOINT
  value: {{ required (printf "%s endpoint is required" .prefix) .store.endpoint | quote }}
- name: {{ .prefix }}_BUCKET
  value: {{ required (printf "%s bucket is required" .prefix) .store.bucket | quote }}
- name: {{ .prefix }}_REGION
  value: {{ default "us-east-1" .store.region | quote }}
{{- if .store.allowedHosts }}
- name: {{ .prefix }}_ALLOWED_HOSTS
  value: {{ join "," .store.allowedHosts | quote }}
{{- end }}
- name: {{ .prefix }}_ALLOW_INSECURE
  value: {{ ternary "true" "false" (default false .store.allowInsecure) | quote }}
{{- if and .store.retention .store.retention.mode }}
- name: {{ .prefix }}_RETENTION_MODE
  value: {{ .store.retention.mode | quote }}
- name: {{ .prefix }}_RETENTION_DAYS
  value: {{ .store.retention.days | quote }}
{{- end }}
- name: {{ .secret }}_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secrets.existingSecret }}
      key: {{ .secret }}_ACCESS_KEY_ID
- name: {{ .secret }}_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secrets.existingSecret }}
      key: {{ .secret }}_SECRET_ACCESS_KEY
{{- end -}}

{{/* the DSN per postgres.mode (D-2). statefulset: built from the chart's own service and the
     POSTGRES_PASSWORD key; external: the full DSN from the secret; cnpg: the operator's app secret. */}}
{{- define "energy-platform.dsnEnv" -}}
{{- if eq .Values.postgres.mode "statefulset" }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.existingSecret }}
      key: POSTGRES_PASSWORD
- name: ENERGY_PLATFORM_DSN
  value: {{ printf "postgresql://%s:$(POSTGRES_PASSWORD)@%s-postgres:5432/%s" .Values.postgres.user (include "energy-platform.fullname" .) .Values.postgres.database | quote }}
{{- else if eq .Values.postgres.mode "external" }}
- name: ENERGY_PLATFORM_DSN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.existingSecret }}
      key: {{ .Values.postgres.external.dsnSecretKey }}
{{- else if eq .Values.postgres.mode "cnpg" }}
- name: ENERGY_PLATFORM_DSN
  valueFrom:
    secretKeyRef:
      name: {{ include "energy-platform.fullname" . }}-pg-app
      key: uri
{{- else }}
{{- fail (printf "postgres.mode %q must be statefulset | cnpg | external" .Values.postgres.mode) }}
{{- end }}
{{- end -}}

{{/* the platform environment every verb pod gets; the smoke passes bronzeMode "dir" (P5-D5) */}}
{{- define "energy-platform.platformEnv" -}}
- name: ENERGY_PLATFORM_TARGETS
  value: /app/targets
- name: ENERGY_PLATFORM_BRONZE
  value: {{ default "s3" .bronzeMode }}
- name: TMPDIR
  value: /tmp
{{ include "energy-platform.dsnEnv" .root }}
{{ include "energy-platform.s3Env" (dict "root" .root "prefix" "ENERGY_PLATFORM_S3" "secret" "BRONZE" "store" .root.Values.bronze) }}
{{- if eq .root.Values.bronze.tiering.mode "move" }}
{{ include "energy-platform.s3Env" (dict "root" .root "prefix" "ENERGY_PLATFORM_S3_COLD" "secret" "BRONZE_COLD" "store" (dict "endpoint" .root.Values.bronze.tiering.coldEndpoint "bucket" .root.Values.bronze.tiering.coldBucket "region" .root.Values.bronze.tiering.coldRegion "allowInsecure" .root.Values.bronze.tiering.coldAllowInsecure)) }}
{{- end }}
{{- end -}}

{{/* one platform container: dict "root" $ "name" "capture" "args" (list ...) */}}
{{- define "energy-platform.container" -}}
- name: {{ .name }}
  image: {{ include "energy-platform.image" .root }}
  imagePullPolicy: {{ .root.Values.image.pullPolicy }}
  args:
{{ toYaml .args | indent 4 }}
  env:
{{ include "energy-platform.platformEnv" (dict "root" .root "bronzeMode" (default "s3" .bronzeMode)) | indent 4 }}
{{- if .extraEnv }}
{{ toYaml .extraEnv | indent 4 }}
{{- end }}
  securityContext:
{{ include "energy-platform.containerSecurity" . | indent 4 }}
  resources:
{{ toYaml .root.Values.resources.job | indent 4 }}
  volumeMounts:
    - name: tmp
      mountPath: /tmp
{{- end -}}

{{/* pod spec skeleton shared by CronJobs and hook Jobs: dict "root" $ "role" "capture" "container" (string) */}}
{{- define "energy-platform.podTemplate" -}}
metadata:
  labels:
{{ include "energy-platform.selectorLabels" .root | indent 4 }}
    energy-platform.io/role: {{ .role }}
{{- if .target }}
    energy-platform.io/target: {{ .target }}
{{- end }}
{{- with .root.Values.podAnnotations }}
  annotations:
{{ toYaml . | indent 4 }}
{{- end }}
spec:
  restartPolicy: Never
  serviceAccountName: {{ include "energy-platform.fullname" .root }}
  automountServiceAccountToken: false
  securityContext:
{{ include "energy-platform.podSecurity" (dict "uid" 10001) | indent 4 }}
  containers:
{{ .container | indent 4 }}
  volumes:
    - name: tmp
      emptyDir: {}
{{- end -}}

{{/* the secret's shape as a comment for operators */}}
{{- define "energy-platform.secretKeys" -}}
POSTGRES_PASSWORD (postgres.mode=statefulset) · ENERGY_PLATFORM_DSN (postgres.mode=external) · BRONZE_ACCESS_KEY_ID · BRONZE_SECRET_ACCESS_KEY · BRONZE_REPLICA_ACCESS_KEY_ID · BRONZE_REPLICA_SECRET_ACCESS_KEY (bronze.replica.enabled) · BRONZE_COLD_ACCESS_KEY_ID · BRONZE_COLD_SECRET_ACCESS_KEY (bronze.tiering.mode=move)
{{- end -}}
