#!/bin/bash
# AqueLyst Hunter - Simple Launch Script
# Starts both the dashboard AND the webhook backend

cd "$(dirname "$0")"

# Setup venv if needed
if [ ! -d "venv" ]; then
    echo "🔧 First-time setup..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    python3 -m pip install -q -r requirements.txt
    echo "✅ Setup complete"
else
    source venv/bin/activate
fi

# Kill any existing processes
pkill -f "streamlit run app.py" 2>/dev/null
pkill -f "webhook_server.py" 2>/dev/null
sleep 1

echo ""
echo "🪝 Starting webhook receiver on port 8502..."
nohup python3 webhook_server.py > /tmp/aquelyst-webhook.log 2>&1 &
WEBHOOK_PID=$!
echo "   PID: $WEBHOOK_PID"

sleep 1

echo "🚀 Starting dashboard on port 8501..."
echo "📊 Dashboard: http://localhost:8501"
echo "🪝 Webhook:   http://localhost:8502/webhook/web3forms"
echo ""
echo "💡 Tip: Go to 'Quick Connect' tab to set up email + webhooks in 2 minutes"
echo ""

python3 -m streamlit run app.py --logger.level=warning
