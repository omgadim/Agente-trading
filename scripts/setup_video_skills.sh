#!/usr/bin/env bash
# Instala las skills de edición de video para Claude Code en un contenedor nuevo.
# Pensado para el "Setup script" del entorno cloud de Claude Code (se ejecuta al arrancar cada sesión).
# Es idempotente: lo que ya está instalado se salta.
#
# Versiones fijadas a los commits revisados. Para actualizar, cambia el commit tras revisar el código nuevo.
set -uo pipefail

FFMPEG_SKILL_VERSION=3.1.1
GHOST_EDITOR_COMMIT=ce172726c36293722b08eb57b5b307d4f06389e8
OPENMONTAGE_COMMIT=195eab24478dc9363326aec437aefc3701635ddf
CLAUDE_SHORTS_COMMIT=a369fad9d84287edbb8fa3ab515f268e770f683b

SKILLS="$HOME/.claude/skills"
mkdir -p "$SKILLS"
FAILED=()

log() { echo "==> $*"; }

# Clona un repo en un commit concreto (shallow).
clone_at() {  # url dir commit
  local url=$1 dir=$2 commit=$3
  if [ -d "$dir/.git" ]; then log "$dir ya existe"; return 0; fi
  git init -q "$dir" && git -C "$dir" remote add origin "$url" \
    && git -C "$dir" fetch -q --depth 1 origin "$commit" \
    && git -C "$dir" checkout -q FETCH_HEAD
}

# 1. ffmpeg-skill (npm)
if [ ! -f "$SKILLS/ffmpeg-skill/SKILL.md" ]; then
  log "ffmpeg-skill $FFMPEG_SKILL_VERSION"
  npx -y "ffmpeg-skill@$FFMPEG_SKILL_VERSION" || FAILED+=(ffmpeg-skill)
fi

# 2. ghost-editor
log "ghost-editor"
if clone_at https://github.com/kurbaitaev/ghost-editor "$SKILLS/ghost-editor" "$GHOST_EDITOR_COMMIT"; then
  pip install -q openai-whisper opencv-python google-genai pillow numpy \
    || pip install -q --user openai-whisper opencv-python google-genai pillow numpy \
    || FAILED+=(ghost-editor-pip)
  # Música y efectos (assets.mixkit.co) y emojis animados (api.github.com, raw.githubusercontent.com).
  # Necesitan esos dominios permitidos en la red del entorno; con timeout para no colgar el arranque.
  GE="$SKILLS/ghost-editor/scripts/library_restore.py"
  timeout 600 python3 "$GE" --music-only >/dev/null 2>&1 || FAILED+=(ghost-editor-musica)
  timeout 600 python3 "$GE" --sfx-only --licensed-only >/dev/null 2>&1 || FAILED+=(ghost-editor-sfx)
  timeout 600 python3 "$GE" --emoji-only >/dev/null 2>&1 || FAILED+=(ghost-editor-emoji-opcional)
else
  FAILED+=(ghost-editor)
fi

# 3. claude-shorts (skill /shorts)
log "claude-shorts"
if clone_at https://github.com/agricidaniel/claude-shorts "$HOME/claude-shorts" "$CLAUDE_SHORTS_COMMIT"; then
  V="$HOME/.shorts-skill"
  [ -d "$V" ] || python3 -m venv "$V"
  # Sin torch: solo detecta GPU; sin él transcribe en CPU (y download.pytorch.org puede estar bloqueado).
  "$V/bin/pip" install -q faster-whisper mediapipe numpy opencv-python || FAILED+=(shorts-pip)
  D="$SKILLS/shorts"
  if [ ! -f "$D/SKILL.md" ]; then
    mkdir -p "$D/scripts" "$D/references" "$D/remotion"
    cp "$HOME/claude-shorts/SKILL.md" "$D/"
    cp "$HOME"/claude-shorts/scripts/*.sh "$HOME"/claude-shorts/scripts/*.py "$D/scripts/" 2>/dev/null
    chmod +x "$D"/scripts/* 2>/dev/null
    cp "$HOME"/claude-shorts/references/*.md "$D/references/" 2>/dev/null
    tar -C "$HOME/claude-shorts/remotion" --exclude=node_modules --exclude=.remotion -cf - . | tar -C "$D/remotion" -xf -
  fi
  [ -d "$D/remotion/node_modules" ] || (cd "$D/remotion" && npm install --silent) || FAILED+=(shorts-npm)
else
  FAILED+=(claude-shorts)
fi

# 4. OpenMontage
log "OpenMontage"
if clone_at https://github.com/calesthio/OpenMontage.git "$HOME/OpenMontage" "$OPENMONTAGE_COMMIT"; then
  [ -x "$HOME/OpenMontage/.venv/bin/python" ] || (cd "$HOME/OpenMontage" && make setup) || FAILED+=(openmontage)
else
  FAILED+=(openmontage)
fi

# 5. Plugin hyperframes
if command -v claude >/dev/null; then
  log "plugin hyperframes"
  claude plugin marketplace list 2>/dev/null | grep -q hyperframes \
    || claude plugin marketplace add heygen-com/hyperframes || FAILED+=(hyperframes-marketplace)
  claude plugin install hyperframes@hyperframes >/dev/null 2>&1 || FAILED+=(hyperframes-plugin)
else
  FAILED+=(hyperframes-sin-cli-claude)
fi

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "AVISO: fallaron: ${FAILED[*]}"
else
  log "Skills de video listas"
fi
exit 0  # no bloquear el arranque de la sesión por una skill opcional
