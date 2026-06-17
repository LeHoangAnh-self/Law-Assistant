#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${CONTAINER:-law-service-redis-1}"
DB="${DB:-2}"
QUEUE="${QUEUE:-celery}"
INTERVAL="${INTERVAL:-10}"

human_duration() {
  local seconds="$1"
  local days=$((seconds / 86400))
  local hours=$(((seconds % 86400) / 3600))
  local minutes=$(((seconds % 3600) / 60))
  local secs=$((seconds % 60))

  if (( days > 0 )); then
    printf "%dd %02dh %02dm %02ds" "$days" "$hours" "$minutes" "$secs"
  elif (( hours > 0 )); then
    printf "%02dh %02dm %02ds" "$hours" "$minutes" "$secs"
  else
    printf "%02dm %02ds" "$minutes" "$secs"
  fi
}

queue_length() {
  docker exec "$CONTAINER" redis-cli -n "$DB" LLEN "$QUEUE" | tr -d '\r'
}

start_time="$(date +%s)"
start_len="$(queue_length)"
prev_time="$start_time"
prev_len="$start_len"

printf "Tracking Redis queue %s/%s:%s every %ss\n" "$CONTAINER" "$DB" "$QUEUE" "$INTERVAL"
printf "Start queue length: %s\n\n" "$start_len"

while true; do
  sleep "$INTERVAL"
  now="$(date +%s)"
  current_len="$(queue_length)"
  delta_jobs=$((prev_len - current_len))
  delta_time=$((now - prev_time))
  total_done=$((start_len - current_len))
  elapsed=$((now - start_time))

  rate_window="$(awk -v jobs="$delta_jobs" -v seconds="$delta_time" 'BEGIN {
    if (seconds <= 0) printf "0.00";
    else printf "%.2f", jobs / seconds;
  }')"
  rate_avg="$(awk -v jobs="$total_done" -v seconds="$elapsed" 'BEGIN {
    if (seconds <= 0) printf "0.00";
    else printf "%.2f", jobs / seconds;
  }')"
  eta_seconds="$(awk -v remaining="$current_len" -v rate="$rate_avg" 'BEGIN {
    if (rate <= 0) print -1;
    else printf "%d", remaining / rate;
  }')"

  if (( eta_seconds < 0 )); then
    eta="unknown"
    finish_at="unknown"
  else
    eta="$(human_duration "$eta_seconds")"
    finish_at="$(date -d "@$((now + eta_seconds))" "+%Y-%m-%d %H:%M:%S")"
  fi

  printf "%s | queue=%s | done=%s | rate=%s/s window, %s/s avg | elapsed=%s | ETA=%s | finish=%s\n" \
    "$(date '+%H:%M:%S')" \
    "$current_len" \
    "$total_done" \
    "$rate_window" \
    "$rate_avg" \
    "$(human_duration "$elapsed")" \
    "$eta" \
    "$finish_at"

  prev_time="$now"
  prev_len="$current_len"
done
