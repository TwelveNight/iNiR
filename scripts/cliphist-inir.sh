#!/usr/bin/env bash
set -euo pipefail
# Share II's native cliphist configuration and database. Decoded temporary
# images remain under iNiR's private runtime directory at the call sites.
exec cliphist "$@"
