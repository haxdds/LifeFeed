import argparse

import uvicorn

from app import config


def main():
    parser = argparse.ArgumentParser(description="Run the LifeFeed server.")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    args = parser.parse_args()

    print(f"LifeFeed running at http://{args.host}:{args.port}  (API docs at /docs)")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
