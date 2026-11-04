#!/usr/bin/env bash
# make doctor: check everything the live demo needs and print a fix for each failure.
set -uo pipefail

MLFLOW_PORT="${MLFLOW_PORT:-5050}"
MCP_PORT="${STANDARDS_MCP_PORT:-8765}"
fails=0

ok()   { printf "  \033[32m✔\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✘\033[0m %s\n      fix: %s\n" "$1" "$2"; fails=$((fails + 1)); }
warn() { printf "  \033[33m!\033[0m %s\n      note: %s\n" "$1" "$2"; }

echo "doctor: checking the demo stack"

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  bad "docker CLI not found" "install Docker Desktop (macOS/Windows+WSL2) or Docker Engine (Linux)"
elif ! docker info >/dev/null 2>&1; then
  bad "Docker daemon not reachable" "start Docker Desktop (or: sudo systemctl start docker) and retry"
else
  ok "Docker daemon reachable ($(docker version --format '{{.Server.Version}}' 2>/dev/null))"
  if docker compose version >/dev/null 2>&1; then
    ok "Docker Compose v2 ($(docker compose version --short 2>/dev/null))"
  else
    bad "docker compose (v2 plugin) not found" "update Docker; the old docker-compose v1 binary is not supported"
  fi
fi

# 2. Ports: either free, or held by this project's containers
port_owner() { docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E "127\.0\.0\.1:$1->|0\.0\.0\.0:$1->" | awk '{print $1}' | head -1; }
port_in_use() {
  if command -v lsof >/dev/null 2>&1; then lsof -iTCP:"$1" -sTCP:LISTEN -n -P >/dev/null 2>&1
  else (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; fi
}
for spec in "MLflow:$MLFLOW_PORT:MLFLOW_PORT" "standards-mcp:$MCP_PORT:STANDARDS_MCP_PORT"; do
  IFS=: read -r label port var <<<"$spec"
  owner="$(port_owner "$port")"
  if [[ "$owner" == ai-native-mle-starter* ]]; then
    ok "port $port is served by $owner"
  elif port_in_use "$port"; then
    bad "port $port ($label) is used by another process" "stop it, or pick another port: $var=<port> make up (and update .mcp.json if you change the MCP port)"
  else
    warn "port $port ($label) is free but nothing is listening" "run: make up"
  fi
done

# 3. MLflow health endpoint
if curl -fsS --max-time 3 "http://localhost:$MLFLOW_PORT/health" >/dev/null 2>&1; then
  ok "MLflow /health responds on http://localhost:$MLFLOW_PORT"
  exp_id="$(curl -fsS --max-time 5 "http://localhost:$MLFLOW_PORT/api/2.0/mlflow/experiments/get-by-name?experiment_name=credit_default" 2>/dev/null \
    | sed -n 's/.*"experiment_id": *"\([0-9]*\)".*/\1/p' | head -1)"
  runs=0
  if [ -n "$exp_id" ]; then
    runs="$(curl -fsS --max-time 5 -X POST "http://localhost:$MLFLOW_PORT/api/2.0/mlflow/runs/search" \
      -H 'Content-Type: application/json' -d "{\"experiment_ids\":[\"$exp_id\"],\"max_results\":200}" 2>/dev/null \
      | grep -o '"run_id"' | wc -l | tr -d ' ')"
  fi
  if [ "${runs:-0}" -ge 3 ]; then ok "demo runs present ($runs runs in MLflow experiment 'credit_default')"
  else bad "demo runs not found in MLflow experiment 'credit_default'" "run: make seed"; fi
else
  bad "MLflow is not responding on http://localhost:$MLFLOW_PORT/health" "run: make up   (logs: docker compose logs mlflow)"
fi

# 4. MCP endpoint: a real MCP initialize request over streamable HTTP
init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"doctor","version":"1"}}}'
resp="$(curl -sS --max-time 5 -X POST "http://localhost:$MCP_PORT/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$init" 2>/dev/null)"
if echo "$resp" | grep -q '"serverInfo"'; then
  ok "standards-mcp answers MCP initialize on http://localhost:$MCP_PORT/mcp"
else
  bad "standards-mcp did not answer MCP initialize" "run: make up   (logs: docker compose logs standards-mcp)"
fi

# 5. Lakehouse
if [ -f lakehouse/_manifest.json ]; then ok "lakehouse snapshot present (lakehouse/_manifest.json)"
else bad "lakehouse not generated" "run: make seed"; fi

# 6. Skills installed for Claude Code and Codex
n_claude=$(find .claude/skills -maxdepth 1 -type l 2>/dev/null | wc -l | tr -d ' ')
n_agents=$(find .agents/skills -maxdepth 1 -type l 2>/dev/null | wc -l | tr -d ' ')
n_src=$(find skills -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')
if [ "$n_claude" = "$n_src" ] && [ "$n_agents" = "$n_src" ]; then ok "skills linked: $n_src in .claude/skills and .agents/skills"
else bad "skills not linked ($n_claude/$n_src claude, $n_agents/$n_src agents)" "run: make skills"; fi

# 7. Claude Code CLI
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code CLI found ($(claude --version 2>/dev/null | head -1))"
  echo "      check MCP wiring with: claude mcp list   (inside a session: /mcp)"
else
  bad "Claude Code CLI not found" "install it: https://code.claude.com/docs/en/setup"
fi

echo ""
if [ "$fails" -eq 0 ]; then echo "doctor: all checks passed"; else echo "doctor: $fails check(s) failed"; fi
exit "$fails"
