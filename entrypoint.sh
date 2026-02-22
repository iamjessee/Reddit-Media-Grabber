#!/bin/sh -e
# Pass all args to main.py. If none provided, program will error.
exec python /app/main.py "$@"