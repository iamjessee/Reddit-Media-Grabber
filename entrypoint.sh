#!/bin/sh -e
# Pass all args to main.py. If none provided, program will prompt for input.
exec python /app/main.py "$@"