"""Lightweight webhook receiver using Python stdlib (no FastAPI dependency).

Receives Web3Forms POST submissions and creates leads automatically.
Runs on port 8502 alongside the Streamlit app on 8501.

Auto-started by launch.sh — no manual setup required.
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import database
import lead_scoring


PORT = 8502


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle Web3Forms webhook submissions."""

    def log_message(self, format, *args):
        # Reduce noise in logs
        pass

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/':
            self._send_json(200, {
                "status": "running",
                "service": "AqueLyst Hunter Webhook Receiver",
                "endpoints": ["POST /webhook/web3forms", "GET /health"]
            })
        elif path == '/health':
            self._send_json(200, {"status": "healthy"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path != '/webhook/web3forms':
            self._send_json(404, {"error": "Unknown endpoint"})
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8', errors='replace')
            content_type = self.headers.get('Content-Type', '')

            # Parse based on content type
            data = {}
            if 'application/json' in content_type:
                data = json.loads(body)
            elif 'application/x-www-form-urlencoded' in content_type:
                parsed = parse_qs(body)
                data = {k: v[0] if v else '' for k, v in parsed.items()}
            elif 'multipart/form-data' in content_type:
                # Simple multipart parsing — Web3Forms uses this
                boundary = content_type.split('boundary=')[-1]
                parts = body.split(f'--{boundary}')
                for part in parts:
                    if 'Content-Disposition' in part and 'name=' in part:
                        try:
                            name = part.split('name="')[1].split('"')[0]
                            value = part.split('\r\n\r\n')[1].split('\r\n--')[0].strip()
                            data[name] = value
                        except (IndexError, ValueError):
                            continue

            # Extract lead fields
            email = (data.get('email') or '').strip()
            business_name = (data.get('business_name')
                             or data.get('company')
                             or data.get('name')
                             or 'Unknown').strip()

            if not email:
                self._send_json(400, {"error": "Missing email field"})
                return

            # Build lead
            lead_data = {
                'business_name': business_name,
                'contact_name': data.get('name', '').strip(),
                'email': email,
                'phone': data.get('phone', '').strip(),
                'website': data.get('website', '').strip(),
                'city': data.get('city', '').strip(),
                'state': data.get('state', '').strip(),
                'business_type': data.get('business_type', '').strip(),
                'message': data.get('message', '').strip(),
                'pain_hypothesis': data.get('main_problem', '').strip()
                                   or data.get('problem', '').strip(),
                'product_fit': data.get('product_interest', '').strip(),
                'lead_source': 'web3forms_webhook',
                'source_channel': 'website_form',
                'notes': f"Auto-imported via webhook. Stalls: {data.get('number_of_stalls', 'N/A')}"
            }

            # Add to database
            lead_id = database.add_lead(**lead_data)
            if not lead_id:
                self._send_json(409, {
                    "error": "Lead with this email already exists",
                    "email": email
                })
                return

            # Auto-score
            score = lead_scoring.calculate_lead_score(lead_data)
            product, _ = lead_scoring.match_product(lead_data)
            database.update_lead(lead_id, lead_score=score, product_fit=product)

            # Log activity
            database.log_activity(
                lead_id,
                "webhook_received",
                f"Auto-imported from website (score: {score})"
            )

            self._send_json(200, {
                "success": True,
                "lead_id": lead_id,
                "business_name": business_name,
                "lead_score": score,
                "message": f"Lead created and scored {score}/100"
            })

        except Exception as e:
            self._send_json(500, {"error": f"Server error: {str(e)}"})


def run(port=PORT):
    """Run the webhook server."""
    database.init_db()  # Make sure DB exists

    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    print(f"🪝 Webhook receiver running on http://localhost:{port}")
    print(f"📨 Endpoint: http://localhost:{port}/webhook/web3forms")
    print(f"💚 Health check: http://localhost:{port}/health")
    print()
    print("Use ngrok to expose publicly:")
    print(f"   ngrok http {port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Webhook receiver stopped")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run(port)
