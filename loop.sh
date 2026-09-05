#!/bin/bash
# ==========================================
# 🔄 CONTINUOUS AUTO-LOOP BACKGROUND DAEMON
# ==========================================

echo "🚀 Starting Autonomous 3-Hour Gaming Agent Loop..."

while true; do
    echo "=========================================="
    echo "⏰ Execution triggered at: $(date)"
    echo "=========================================="

    if [ -f .env ]; then
        export $(cat .env | grep -v '#' | xargs)
    fi

    bash run.sh

    echo "⏳ Waiting for 3 hours before the next check..."
    sleep 24800
done
