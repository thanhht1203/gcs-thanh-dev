from __future__ import annotations

import uvicorn

from .config import load_settings, parse_cli
from .engine import Engine, create_app


def main() -> None:
    args = parse_cli()
    settings = load_settings(args.config, sim_override=True if args.sim else None)
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    print(f"EO service  http://{settings.host}:{settings.port}  sim={settings.sim}")
    engine = Engine(settings, webcam=args.webcam)
    app = create_app(engine)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
