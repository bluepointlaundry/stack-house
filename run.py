"""Start Stack House.

    python run.py                 # http://localhost:8000
    python run.py --port 9000
    python run.py --host 0.0.0.0  # reachable from other devices on your network
"""
import argparse
import os

from app import create_app


def main():
    parser = argparse.ArgumentParser(description="Run the Stack House kitchen app")
    parser.add_argument("--host", default=os.environ.get("STACKHOUSE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--data", help="folder for the database and photos (default: ./data)")
    args = parser.parse_args()
    if args.data:
        os.environ["STACKHOUSE_DATA"] = os.path.abspath(args.data)

    app = create_app()
    from waitress import serve

    print(f"Stack House is running on http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}")
    serve(app, host=args.host, port=args.port, threads=16)


if __name__ == "__main__":
    main()
