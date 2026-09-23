{{/* postgresql.conf and pg_hba.conf for postgres.mode=statefulset; the pod's checksum/config annotation
follows this content, so an hba or parameter change restarts Postgres (ADR-036 §4). */}}
{{- define "energy-platform.postgresConfig" -}}
postgresql.conf: |
  listen_addresses = '*'
  port = 5432
  max_connections = 50
  shared_buffers = 128MB
  timezone = 'UTC'
  log_timezone = 'UTC'
  wal_level = replica
  archive_mode = on
  # ADR-036 amendment 1: gzip -n (same segment, same bytes) via .part + rename; a segment already
  # archived with identical content is success (a retry), different content fails
  archive_command = 'f=/wal-archive/%f.gz; if [ -f "$f" ]; then gzip -dc "$f" | cmp -s - %p; else gzip -n -c %p > "$f.part" && mv "$f.part" "$f"; fi'
  archive_timeout = 300
  unix_socket_directories = '/var/run/postgresql'
pg_hba.conf: |
  local   all  all              trust
  host    all  all  127.0.0.1/32 scram-sha-256
  host    all  all  ::1/128      scram-sha-256
  host    all  all  0.0.0.0/0    scram-sha-256
  host    all  all  ::/0         scram-sha-256
  # pg_basebackup (the pg-backup CronJob, ADR-036 §4) opens a replication connection
  host    replication  all  0.0.0.0/0  scram-sha-256
  host    replication  all  ::/0       scram-sha-256
{{- end -}}

{{/* ADR-036 amendment 1 §6: every archive path carries the cluster's system identifier, so a
re-initialised cluster (new deploy, Bronze-only rebuild) never collides with the locked WAL of
an earlier one. Writes the identifier to the given file and refuses anything but digits.
dict "root" $ "out" "/work/SYSTEM_ID" */}}
{{- define "energy-platform.systemIdScript" -}}
{{ include "energy-platform.waitForPostgres" .root }}
psql -h {{ include "energy-platform.fullname" .root }}-postgres -U {{ .root.Values.postgres.user }} -d {{ .root.Values.postgres.database }} -Atc "select system_identifier from pg_control_system()" > {{ .out }}
grep -Eq '^[0-9]+$' {{ .out }} || { echo "system identifier unreadable: $(cat {{ .out }})" >&2; exit 1; }
{{- end -}}

{{/* A pod that connects to Postgres the moment it starts can be refused while the CNI is still
adding the NetworkPolicy allow rule for its new IP (k3s kube-router rejects until then; the
first demo runs of pg-wal-ship failed with "Connection refused", the same Job delayed by 15 s
succeeded). Wait for the server to answer, up to 60 s, before the first connection. */}}
{{- define "energy-platform.waitForPostgres" -}}
for i in $(seq 1 30); do pg_isready -q -h {{ include "energy-platform.fullname" . }}-postgres -p 5432 -t 2 && break; sleep 2; done
pg_isready -h {{ include "energy-platform.fullname" . }}-postgres -p 5432 -t 2 || { echo "Postgres not reachable after 60 s" >&2; exit 1; }
{{- end -}}
