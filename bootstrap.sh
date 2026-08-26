#!/usr/bin/env bash
# EXEQ Hub — sobe ambiente local (Docker + deps + migrate + app)
# Uso:
#   ./bootstrap.sh              # docker + migrate + runserver (foreground)
#   ./bootstrap.sh --bg         # processos em background (logs em .bootstrap/)
#   ./bootstrap.sh --no-celery  # só web
#   ./bootstrap.sh --down       # para containers e processos do bootstrap
#   ./bootstrap.sh --check      # só health check
#
# Windows: Git Bash ou WSL. PowerShell: bash bootstrap.sh  /  sh bootstrap.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BG=0
WITH_CELERY=1
MODE_UP=1
MODE_CHECK=0
MODE_DOWN=0

for arg in "$@"; do
  case "$arg" in
    --bg) BG=1 ;;
    --no-celery) WITH_CELERY=0 ;;
    --down) MODE_DOWN=1; MODE_UP=0 ;;
    --check) MODE_CHECK=1; MODE_UP=0 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Flag desconhecida: $arg (use --help)" >&2
      exit 2
      ;;
  esac
done

LOG_DIR="$ROOT/.bootstrap"
PID_DIR="$LOG_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

log() { echo "[bootstrap] $*"; }
die() { echo "[bootstrap] ERRO: $*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

pick_python() {
  if have python; then
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null && { echo python; return; }
  fi
  if have python3; then
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null && { echo python3; return; }
  fi
  if have py; then
    # Windows py launcher
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null && { echo "py -3"; return; }
  fi
  die "Python 3.11+ não encontrado no PATH"
}

PY="$(pick_python)"
run_py() { # shellcheck disable=SC2086
  $PY "$@"
}

wait_docker() {
  local i
  for i in $(seq 1 36); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    log "Aguardando Docker Desktop... ($i/36)"
    sleep 5
  done
  die "Docker não respondeu. Abra o Docker Desktop e rode de novo."
}

wait_postgres() {
  local i
  for i in $(seq 1 30); do
    if docker exec exeq_hub_db pg_isready -U exeq -d exeq_hub >/dev/null 2>&1; then
      log "Postgres healthy (5433)"
      return 0
    fi
    sleep 2
  done
  die "Postgres não ficou ready a tempo"
}

http_ok() {
  local url="$1"
  if have curl; then
    curl -fsS -o /dev/null -m 5 "$url" && return 0
    return 1
  fi
  run_py - <<PY
import urllib.request
try:
    urllib.request.urlopen("$url", timeout=5)
except Exception:
    raise SystemExit(1)
PY
}

stop_pids() {
  local name pidfile pid
  for name in runserver celery-worker celery-beat; do
    pidfile="$PID_DIR/$name.pid"
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile" 2>/dev/null || true)"
      if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
        log "Parando $name (pid $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 0.5
        kill -9 "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    fi
  done
}

if [[ "$MODE_DOWN" -eq 1 ]]; then
  log "Derrubando ambiente..."
  stop_pids
  if have docker; then
    docker compose down || true
  fi
  log "OK — containers e processos bootstrap parados."
  exit 0
fi

have docker || die "docker não encontrado no PATH"
docker compose version >/dev/null 2>&1 || die "docker compose não disponível"

if [[ "$MODE_CHECK" -eq 1 ]]; then
  log "Health check..."
  docker compose ps || true
  http_ok "http://127.0.0.1:8000/app/" && log "OK  /app/" || log "FAIL /app/"
  http_ok "http://127.0.0.1:8000/hub/login/" && log "OK  /hub/login/" || log "FAIL /hub/login/"
  http_ok "http://127.0.0.1:8000/admin/login/" && log "OK  /admin/" || log "FAIL /admin/"
  exit 0
fi

# --- up ---
log "Raiz: $ROOT"
log "Python: $PY ($(run_py -c 'import sys; print(sys.version.split()[0])'))"

if ! docker info >/dev/null 2>&1; then
  if [[ -x "/c/Program Files/Docker/Docker/Docker Desktop.exe" ]]; then
    log "Iniciando Docker Desktop..."
    "/c/Program Files/Docker/Docker/Docker Desktop.exe" >/dev/null 2>&1 &
  elif [[ -x "/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe" ]]; then
    log "Iniciando Docker Desktop (WSL)..."
    "/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe" >/dev/null 2>&1 &
  else
    log "Docker parado — tente abrir o Docker Desktop manualmente."
  fi
  wait_docker
fi

log "docker compose up -d (Postgres :5433, Redis :6379)"
docker compose up -d
wait_postgres

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    log "Criado .env a partir de .env.example — revise secrets se for piloto."
  else
    die ".env e .env.example ausentes"
  fi
fi

log "pip install -r requirements.txt"
run_py -m pip install -q -r requirements.txt

log "migrate"
run_py manage.py migrate --noinput

log "admin plataforma (lab: admin@local / admin)"
run_py manage.py ensure_platform_admin

log "django check"
run_py manage.py check

# reinicia processos do bootstrap se --bg ou se já há port 8000
if [[ "$BG" -eq 1 ]]; then
  stop_pids
fi

start_bg() {
  local name="$1"; shift
  local logfile="$LOG_DIR/$name.log"
  local pidfile="$PID_DIR/$name.pid"
  log "start $name → $logfile"
  # nohup no Windows Git Bash costuma funcionar; redireciona stdout/err
  nohup "$@" >"$logfile" 2>&1 &
  echo $! >"$pidfile"
}

if [[ "$BG" -eq 1 ]]; then
  start_bg runserver $PY manage.py runserver 0.0.0.0:8000
  if [[ "$WITH_CELERY" -eq 1 ]]; then
    # solo: Windows-friendly
    start_bg celery-worker $PY -m celery -A config worker -l info -P solo
    start_bg celery-beat $PY -m celery -A config beat -l info
  fi
  sleep 3
  log "URLs:"
  log "  Hub V4:  http://127.0.0.1:8000/hub/"
  log "  SPA:     http://127.0.0.1:8000/app/"
  log "  Admin:   http://127.0.0.1:8000/admin/"
  log "Logs: $LOG_DIR/  |  Parar: ./bootstrap.sh --down"
  http_ok "http://127.0.0.1:8000/app/" && log "Health /app OK" || log "Health /app ainda aquecendo (veja $LOG_DIR/runserver.log)"
  exit 0
fi

# foreground: celery em background interno, runserver no terminal
if [[ "$WITH_CELERY" -eq 1 ]]; then
  start_bg celery-worker $PY -m celery -A config worker -l info -P solo
  start_bg celery-beat $PY -m celery -A config beat -l info
  trap 'stop_pids; exit 0' INT TERM
fi

log "URLs:"
log "  Hub V4:  http://127.0.0.1:8000/hub/"
log "  SPA:     http://127.0.0.1:8000/app/"
log "  Admin:   http://127.0.0.1:8000/admin/"
log "runserver em foreground (Ctrl+C encerra)..."
# shellcheck disable=SC2086
exec $PY manage.py runserver 0.0.0.0:8000
