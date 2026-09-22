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
  archive_command = 'test ! -f /wal-archive/%f && cp %p /wal-archive/%f'
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
