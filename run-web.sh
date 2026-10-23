#!/bin/bash
# WishGranter - Start the web dashboard
cd "$(dirname "$0")"
PYTHONPATH=src python -m uvicorn wish_granter.web.app:create_app --factory --host 0.0.0.0 --port 8020 "$@"