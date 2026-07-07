"""
server.py — Production-ready HTTP Server for Docker & Render.com
==================================================================
This lightweight, multithreaded web server serves the Intelligent Candidate
Discovery Engine web dashboard and API results.

Key Features for Cloud Deployment (Render.com / Docker):
  1. Respects the $PORT environment variable (defaulting to 8000).
  2. Auto-checks if `output/team_ai_rankers.csv` exists on startup. If missing,
     it runs `src/main.py` automatically to generate the baseline top 100 results.
  3. Implements strict `Cache-Control: no-cache` headers for dynamic files
     (CSV, JSON, HTML) so that when an inactive session refreshes or tab closes,
     no stale client-side data persists.
  4. Guarantees 0 MB disk storage usage for file uploads: all CSV file uploads
     are processed client-side in the browser tab via FileReader.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_CSV = PROJECT_ROOT / "output" / "team_ai_rankers.csv"
MAIN_SCRIPT = PROJECT_ROOT / "src" / "main.py"

class CleanCacheHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Prevent browser and proxy caching of dynamic outputs and HTML sessions
        if self.path.endswith('.csv') or self.path.endswith('.json') or self.path.endswith('.html') or self.path == '/':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        # Redirect root / to dashboard.html
        if self.path == '/':
            self.path = '/dashboard.html'
        return super().do_GET()

    def do_POST(self):
        # In our architecture, CSV file uploads are handled 100% in the browser tab via FileReader
        # to guarantee 0 MB disk usage on Render.com (protecting the 512MB storage limit).
        if self.path == '/upload':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                "status": "success",
                "message": "File processed in client tab memory. Zero disk storage used on server."
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404, "Endpoint Not Found")

def ensure_baseline_results():
    """Check if output CSV exists; if not, run main pipeline to generate it."""
    if OUTPUT_CSV.exists():
        print(f"[OK] Found baseline results at: {OUTPUT_CSV}")
        return

    print("[!] No results CSV found. Running backend pipeline (src/main.py)...")
    try:
        res = subprocess.run([sys.executable, str(MAIN_SCRIPT)], check=True)
        if res.returncode == 0:
            print("[OK] Pipeline completed successfully. Baseline results generated.")
        else:
            print("[WARN] Pipeline exited with non-zero status.")
    except Exception as e:
        print(f"[ERROR] Failed to run backend pipeline: {e}")

def run_server():
    # Render.com provides the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    
    # Ensure baseline results exist before serving
    ensure_baseline_results()
    
    # Change working directory to project root so static files are served correctly
    os.chdir(str(PROJECT_ROOT))
    
    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, CleanCacheHTTPRequestHandler)
    
    print("=" * 72)
    print(" INTELLIGENT CANDIDATE DISCOVERY ENGINE - WEB SERVER")
    print("=" * 72)
    print(f"  Listening on: http://0.0.0.0:{port}")
    print(f"  Dashboard   : http://0.0.0.0:{port}/dashboard.html")
    print(f"  Storage     : Client-side tab isolation (0 MB server disk used)")
    print("=" * 72)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
