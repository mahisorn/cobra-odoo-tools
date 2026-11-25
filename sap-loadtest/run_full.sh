#!/bin/bash
# Resumable full load: restart the loader after a crash (skip-existing makes reruns safe). Max 10 attempts.
cd "$(dirname "$0")"
for i in $(seq 1 10); do
  echo "--- attempt $i $(date '+%F %T')" >> full_run.log
  python3 load_sap.py --apply >> full_run.log 2>&1 && { echo "--- finished $(date '+%F %T')" >> full_run.log; exit 0; }
  sleep 60
done
echo "--- gave up $(date '+%F %T')" >> full_run.log; exit 1
