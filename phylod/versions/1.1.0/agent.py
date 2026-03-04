from http.server import HTTPServer, BaseHTTPRequestHandler
import json

VERSION = "1.1.0"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"version": VERSION, "status": "healthy"})
        elif self.path == "/":
            self._respond(200, {"message": f"Phylo Agent {VERSION} running"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # suppress request logging

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print(f"Agent {VERSION} listening on :8080")
    server.serve_forever()
