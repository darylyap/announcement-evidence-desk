def main():
    """Run on a dedicated port; never evict an existing process."""
    import argparse
    import os
    import socket
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.getenv("PORT", "8012")))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--reload", action="store_true")
    a = p.parse_args()
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        os.environ["REQUIRE_ACCESS_KEY"] = "1"
    if a.reload:
        print("Finish active analyses before reloading the server.", flush=True)
    try:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((a.host, a.port))
    except OSError:
        p.exit(1, f"Port {a.port} is occupied. Run ./run.sh --port {a.port + 1}\n")
    print(f"Announcement Evidence Desk: http://{a.host}:{a.port}", flush=True)
    import uvicorn

    uvicorn.run("desk.main:app", host=a.host, port=a.port, reload=a.reload)


if __name__ == "__main__":
    main()
