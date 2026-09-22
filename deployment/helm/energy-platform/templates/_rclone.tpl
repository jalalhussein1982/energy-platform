{{/*
rclone remotes from the environment (no config file): dict "root" $ "alias" "A" "store" <store values> "secret" "BRONZE"
The alias is the rclone remote name (A = store A, B = store B, COLD = the cold location).
*/}}
{{- define "energy-platform.rcloneEnv" -}}
- name: RCLONE_CONFIG_{{ .alias }}_TYPE
  value: s3
- name: RCLONE_CONFIG_{{ .alias }}_PROVIDER
  value: Other
- name: RCLONE_CONFIG_{{ .alias }}_ENDPOINT
  value: {{ required (printf "%s endpoint is required" .alias) .store.endpoint | quote }}
- name: RCLONE_CONFIG_{{ .alias }}_REGION
  value: {{ default "us-east-1" .store.region | quote }}
- name: RCLONE_CONFIG_{{ .alias }}_FORCE_PATH_STYLE
  value: "true"
- name: RCLONE_CONFIG_{{ .alias }}_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secrets.existingSecret }}
      key: {{ .secret }}_ACCESS_KEY_ID
- name: RCLONE_CONFIG_{{ .alias }}_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secrets.existingSecret }}
      key: {{ .secret }}_SECRET_ACCESS_KEY
{{- end -}}

{{/* one rclone container: dict "root" $ "name" "replicate" "script" (string) "env" (rendered env yaml) "mounts" (list of dicts) */}}
{{- define "energy-platform.rcloneContainer" -}}
- name: {{ .name }}
  image: {{ include "energy-platform.thirdPartyImage" .root.Values.rclone.image }}
  command: ["/bin/sh", "-ec"]
  args:
    - |
{{ .script | indent 6 }}
  env:
    - name: RCLONE_CONFIG
      value: /tmp/rclone.conf
    - name: HOME
      value: /tmp
{{ .env | indent 4 }}
  securityContext:
{{ include "energy-platform.containerSecurity" . | indent 4 }}
  resources:
{{ toYaml .root.Values.resources.rclone | indent 4 }}
  volumeMounts:
    - name: tmp
      mountPath: /tmp
{{- range .mounts }}
    - name: {{ .name }}
      mountPath: {{ .mountPath }}
{{- if .readOnly }}
      readOnly: true
{{- end }}
{{- end }}
{{- end -}}
