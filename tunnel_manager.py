"""ngrok tunnel manager — exposes local webhook publicly so Web3Forms can reach it.

Falls back gracefully if ngrok isn't installed. User can install with: brew install ngrok
"""

import subprocess
import shutil
import json
import time
import requests


def is_ngrok_installed():
    """Check if ngrok is on PATH."""
    return shutil.which("ngrok") is not None


def get_install_instructions():
    """Get platform-appropriate install instructions for ngrok."""
    return {
        "macos_brew": "brew install ngrok",
        "macos_dmg": "https://ngrok.com/download",
        "linux": "https://ngrok.com/download",
        "windows": "https://ngrok.com/download",
        "after_install": "Sign up free at ngrok.com → get your auth token → run: ngrok config add-authtoken YOUR_TOKEN"
    }


def is_tunnel_running(port=8502):
    """Check if an ngrok tunnel is active for the given port."""
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        if response.status_code == 200:
            tunnels = response.json().get('tunnels', [])
            for tunnel in tunnels:
                addr = tunnel.get('config', {}).get('addr', '')
                if str(port) in addr:
                    return True, tunnel.get('public_url')
    except Exception:
        pass
    return False, None


def get_tunnel_url(port=8502):
    """Get the public URL of the running tunnel for given port."""
    is_running, url = is_tunnel_running(port)
    return url if is_running else None


def start_tunnel(port=8502):
    """Start ngrok tunnel for the webhook port. Returns (success, url_or_error)."""
    if not is_ngrok_installed():
        return False, "ngrok not installed. Run: brew install ngrok"

    # Check if already running
    is_running, existing_url = is_tunnel_running(port)
    if is_running:
        return True, existing_url

    # Start ngrok in background
    try:
        subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Wait up to 5 seconds for tunnel to come up
        for _ in range(10):
            time.sleep(0.5)
            is_running, url = is_tunnel_running(port)
            if is_running and url:
                return True, url

        return False, "Tunnel failed to start within 5 seconds. Check ngrok auth: ngrok config add-authtoken YOUR_TOKEN"

    except Exception as e:
        return False, f"Failed to start ngrok: {str(e)}"


def stop_tunnel():
    """Stop all ngrok processes."""
    try:
        subprocess.run(["pkill", "-f", "ngrok http"], check=False, capture_output=True)
        return True
    except Exception:
        return False
