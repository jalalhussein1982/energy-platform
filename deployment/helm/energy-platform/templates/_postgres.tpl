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
