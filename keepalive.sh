#!/bin/bash
# Keep server and tunnel alive until 2026-06-09 09:00 CST
set -e

while true; do
  # Check if past deadline (June 9, 2026, 09:00 CST = 2026-06-09 01:00 UTC)
  NOW=$(date +%s)
  DEADLINE=$(date -j -f '%Y-%m-%d %H:%M' '2026-06-09 09:00' +%s 2>/dev/null)
  if [ -n "$DEADLINE" ] && [ "$NOW" -ge "$DEADLINE" ]; then
    echo "[$(date)] Deadline reached (June 9 09:00), stopping."
    kill $(pgrep -f cloudflared) 2>/dev/null
    kill $(pgrep -f "python3.*server.py") 2>/dev/null
    exit 0
  fi
  
  # Restart server if not running
  if ! curl -s -o /dev/null http://localhost:8765/api/stats; then
    echo "[$(date)] Starting server..."
    nohup python3 /Users/doublle/Desktop/追星助手/server.py >> /tmp/server.log 2>&1 &
    sleep 2
  fi
  
  # Restart tunnel if not running
  if ! pgrep -f cloudflared > /dev/null; then
    echo "[$(date)] Starting cloudflared tunnel..."
    nohup /Users/doublle/.local/bin/cloudflared tunnel --url http://localhost:8765 >> /tmp/cf.log 2>&1 &
    sleep 5
    URL=$(grep -o 'https://[a-z0-9.-]*\.trycloudflare\.com' /tmp/cf.log | tail -1)
    if [ -n "$URL" ]; then
      echo "[$(date)] Tunnel URL: $URL"
      echo "$URL" > /tmp/current_tunnel_url.txt
    fi
  fi
  
  sleep 60
done
