#!/usr/bin/env bash

set -u

REPO_DIR="${1:-$PWD}"
SESSIONS_FILE="${CLAUDE_API_SESSIONS_FILE:-/tmp/claude_api_sessions.txt}"
VARS_RE='ANTHROPIC_(API_KEY|AUTH_TOKEN)'
LINE_RE="^[[:space:]]*((export|typeset[[:space:]]+-x|declare[[:space:]]+-x)[[:space:]]+)?${VARS_RE}=|^[[:space:]]*launchctl[[:space:]]+setenv[[:space:]]+${VARS_RE}([[:space:]]|\$)|^[[:space:]]*set[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*${VARS_RE}([[:space:]]|\$)|^SETUVAR[[:space:]]+(--export[[:space:]]+)?${VARS_RE}:"

CHANGED=0
WARNINGS=0

say()  { printf '%s\n' "$*"; }
warn() { printf 'ATTENTION: %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }

backup() {
  local f="$1" b="$1.bak"
  [ -e "$b" ] && b="$1.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "$f" "$b" && say "  sauvegarde : $b"
}

rewrite_with_sed() {
  local f="$1"; shift
  local tmp; tmp="$(mktemp "${TMPDIR:-/tmp}/dakauth.XXXXXX")" || return 1
  if sed -E "$@" "$f" > "$tmp"; then cat "$tmp" > "$f"; fi
  rm -f "$tmp"
}

clean_lines() {
  local f="$1"
  [ -f "$f" ] || return 0
  local nums; nums="$(grep -nE "$LINE_RE" "$f" 2>/dev/null | cut -d: -f1 | tr '\n' ' ')"
  [ -n "${nums// /}" ] || return 0
  if [ ! -w "$f" ]; then
    for n in $nums; do warn "$f:$n définit une clé API mais n'est pas modifiable (relancer avec sudo)"; done
    return 0
  fi
  for n in $nums; do say "supprimé : $f:$n"; done
  backup "$f"
  rewrite_with_sed "$f" -e "/${LINE_RE//\//\\/}/d"
  CHANGED=$((CHANGED + 1))
}

resolve_path() {
  local w="$1" base="$2"
  w="${w#\"}"; w="${w%\"}"; w="${w#\'}"; w="${w%\'}"
  case "$w" in
    "~/"*)         w="$HOME/${w#\~/}" ;;
    '$HOME/'*)     w="$HOME/${w#\$HOME/}" ;;
    '${HOME}/'*)   w="$HOME/${w#\$\{HOME\}/}" ;;
  esac
  case "$w" in
    ''|-*|'$'*|'.'|'..') return 1 ;;
    /*) [ -f "$w" ] && { printf '%s\n' "$w"; return 0; } ;;
    *)  for d in "$base" "$HOME"; do [ -f "$d/$w" ] && { printf '%s\n' "$d/$w"; return 0; }; done ;;
  esac
  return 1
}

clean_source_lines() {
  local f="$1"
  [ -f "$f" ] || return 0
  local base; base="$(cd "$(dirname "$f")" && pwd)"
  local n=0 line del=() w p
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    case "${line#"${line%%[![:space:]]*}"}" in '#'*) continue ;; esac
    printf '%s' "$line" | grep -qE '(^|[;&|([:space:]])(source|\.|dotenv|dotenv_if_exists|source_env|cat|xargs|env_file)([[:space:]]|$)|set[[:space:]]+-a' || continue
    set -f
    for w in $(printf '%s' "$line" | tr ';&|()`<>' '        '); do
      p="$(resolve_path "$w" "$base")" || continue
      [ "$p" = "$f" ] && continue
      if grep -qE "^[[:space:]]*(export[[:space:]]+)?${VARS_RE}=|^[[:space:]]*set[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*${VARS_RE}([[:space:]]|\$)" "$p" 2>/dev/null; then
        say "supprimé : $f:$n (chargeait $p — fichier conservé)"
        del+=("-e" "${n}d")
        break
      fi
    done
    set +f
  done < "$f"
  [ "${#del[@]}" -gt 0 ] || return 0
  if [ ! -w "$f" ]; then warn "$f n'est pas modifiable (relancer avec sudo)"; return 0; fi
  backup "$f"
  rewrite_with_sed "$f" "${del[@]}"
  CHANGED=$((CHANGED + 1))
}

clean_json() {
  local f="$1"
  [ -f "$f" ] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    grep -qE "\"(${VARS_RE}|apiKeyHelper)\"" "$f" && warn "$f contient une entrée clé API mais python3 est absent"
    return 0
  fi
  python3 - "$f" <<'PY'
import json, os, re, shutil, sys, time
path = sys.argv[1]
try:
    raw = open(path, encoding="utf-8").read()
    data = json.loads(raw) if raw.strip() else {}
except Exception as e:
    print(f"ATTENTION: {path} : JSON illisible ({type(e).__name__}), ignoré")
    sys.exit(0)
if not isinstance(data, dict):
    sys.exit(0)
def lineno(key):
    for i, l in enumerate(raw.splitlines(), 1):
        if re.search(r'"%s"\s*:' % re.escape(key), l):
            return i
    return "?"
removed = []
env = data.get("env")
if isinstance(env, dict):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if k in env:
            removed.append((f"env.{k}", lineno(k)))
            del env[k]
    if not env:
        del data["env"]
if "apiKeyHelper" in data:
    removed.append(("apiKeyHelper", lineno("apiKeyHelper")))
    del data["apiKeyHelper"]
if not removed:
    sys.exit(0)
if not os.access(path, os.W_OK):
    for k, n in removed:
        print(f"ATTENTION: {path}:{n} ({k}) non modifiable (relancer avec sudo)")
    sys.exit(0)
bak = path + ".bak"
if os.path.exists(bak):
    bak = path + ".bak." + time.strftime("%Y%m%d%H%M%S")
shutil.copy2(path, bak)
for k, n in removed:
    print(f"supprimé : {path}:{n} ({k})")
print(f"  sauvegarde : {bak}")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY
}

say "== Désactivation de l'auth Claude Code par clé API =="
say "HOME=$HOME  repo=$REPO_DIR"

RC_FILES=(
  "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.zlogin"
  "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"
  "$HOME/.config/fish/config.fish" "$HOME/.config/fish/fish_variables"
)
if [ -n "${ZDOTDIR:-}" ] && [ "$ZDOTDIR" != "$HOME" ]; then
  RC_FILES+=("$ZDOTDIR/.zshenv" "$ZDOTDIR/.zprofile" "$ZDOTDIR/.zshrc" "$ZDOTDIR/.zlogin")
fi
for f in "$HOME"/.config/fish/conf.d/*.fish "$HOME"/.oh-my-zsh/custom/*.zsh; do [ -f "$f" ] && RC_FILES+=("$f"); done

ENVRC_FILES=()
while IFS= read -r f; do ENVRC_FILES+=("$f"); done < <(
  { find "$HOME" -maxdepth 5 \( -name node_modules -o -name .venv -o -name venv -o -name Library -o -name .git -o -name .Trash -o -name .cache \) -prune -o -name .envrc -type f -print 2>/dev/null
    [ -d "$REPO_DIR" ] && find "$REPO_DIR" -maxdepth 4 \( -name node_modules -o -name .venv -o -name .git \) -prune -o -name .envrc -type f -print 2>/dev/null
  } | sort -u)

SYS_FILES=(/etc/zshenv /etc/zprofile /etc/zshrc /etc/profile /etc/bashrc /etc/bash.bashrc /etc/environment /etc/launchd.conf)
for f in /etc/profile.d/*.sh; do [ -f "$f" ] && SYS_FILES+=("$f"); done

say "-- Fichiers shell inspectés --"
for f in "${RC_FILES[@]}" "${ENVRC_FILES[@]}" "${SYS_FILES[@]}"; do
  [ -f "$f" ] && say "  $f"
done

say "-- Suppression des lignes de clé --"
for f in "${RC_FILES[@]}" "${ENVRC_FILES[@]}" "${SYS_FILES[@]}"; do clean_lines "$f"; done

say "-- Lignes qui chargent un .env/secret contenant la clé --"
for f in "${RC_FILES[@]}" "${ENVRC_FILES[@]}" "${SYS_FILES[@]}"; do clean_source_lines "$f"; done

say "-- settings.json de Claude Code --"
for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" \
         "$REPO_DIR/.claude/settings.json" "$REPO_DIR/.claude/settings.local.json"; do
  [ -f "$f" ] && say "  inspecté : $f"
  clean_json "$f"
done
for f in "/Library/Application Support/ClaudeCode/managed-settings.json" /etc/claude-code/managed-settings.json; do
  [ -f "$f" ] && grep -qE "\"(${VARS_RE}|apiKeyHelper)\"" "$f" && warn "$f (paramètres gérés) contient une entrée clé API — à voir avec l'admin"
done

if [ -d "$HOME/Library/LaunchAgents" ]; then
  for f in "$HOME"/Library/LaunchAgents/*.plist; do
    [ -f "$f" ] && grep -qE "$VARS_RE" "$f" && warn "$f mentionne une clé API (LaunchAgent) : $(grep -nE "$VARS_RE" "$f" | cut -d: -f1 | tr '\n' ' ')"
  done
fi
if [ -f "$HOME/.claude.json" ] && grep -qE '"(primaryApiKey|customApiKeyResponses)"' "$HOME/.claude.json"; then
  warn "$HOME/.claude.json contient primaryApiKey/customApiKeyResponses (clé saisie via /login) : dans claude, faire /logout puis /login avec le compte Claude Max"
fi

if command -v launchctl >/dev/null 2>&1; then
  for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN; do
    if [ -n "$(launchctl getenv "$v" 2>/dev/null)" ]; then
      launchctl unsetenv "$v" && say "launchctl unsetenv $v (était défini)"
    else
      launchctl unsetenv "$v" 2>/dev/null || true
    fi
  done
else
  say "launchctl absent (pas macOS) : étape ignorée"
fi

for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN; do
  if [ -n "${!v:-}" ]; then
    warn "$v est encore défini dans ce terminal : fermez-le (ou 'unset $v') avant de relancer claude"
  fi
done

: > "$SESSIONS_FILE" 2>/dev/null || warn "impossible d'écrire $SESSIONS_FILE"
PS_LIST="$(ps -ax -o pid=,command= 2>/dev/null)" || PS_LIST=""
printf '%s\n' "$PS_LIST" | awk -v self="$$" '
  $1 == self { next }
  {
    cmd = $2; n = split(cmd, parts, "/"); base = parts[n]
    if (base == "claude" || $0 ~ /@anthropic-ai\/claude-code/ || $0 ~ /claude-code\/cli\.js/) print $1
  }' | while read -r pid; do
  [ -n "$pid" ] || continue
  if ps eww -o command= -p "$pid" 2>/dev/null | grep -q 'ANTHROPIC_API_KEY='; then
    printf '%s\n' "$pid" >> "$SESSIONS_FILE"
  fi
done
N_SESS=$(wc -l < "$SESSIONS_FILE" 2>/dev/null | tr -d ' ')
say "-- Sessions claude encore lancées avec ANTHROPIC_API_KEY : ${N_SESS:-0} (PID dans $SESSIONS_FILE, non tuées) --"

say ""
say "Terminé : ${CHANGED} fichier(s) shell modifié(s) (les JSON modifiés sont listés ci-dessus), ${WARNINGS} avertissement(s)."
say "RAPPEL : ouvrez un NOUVEAU terminal, lancez 'claude' puis tapez '/status' :"
say "         l'authentification doit indiquer 'Claude Max' (et non 'API key')."
say "         Les sessions listées dans $SESSIONS_FILE gardent la clé tant qu'elles ne sont pas relancées."
