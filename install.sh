#!/bin/sh
# hermes-office-3d installer.
#
#   curl -fsSL https://raw.githubusercontent.com/pyxl-dev/hermes-office-3d/main/install.sh | sh
#   ./install.sh               # from a clone: installs that clone
#   ./install.sh --uninstall
#
# Puts the code in ~/.local/share/hermes-office-3d (or uses this clone) and
# adds a `hermes-office-3d` command to ~/.local/bin. Re-run it to update.
# Nothing outside your home folder is touched.
set -eu

REPO="${HERMES_OFFICE_REPO:-https://github.com/pyxl-dev/hermes-office-3d.git}"
DEST="${HERMES_OFFICE_HOME:-$HOME/.local/share/hermes-office-3d}"
BIN="$HOME/.local/bin"
LAUNCHER="$BIN/hermes-office-3d"
MARK="# hermes-office-3d launcher (managed by install.sh)"

if [ -t 1 ]; then B=$(printf '\033[1m'); G=$(printf '\033[32m'); Y=$(printf '\033[33m'); R=$(printf '\033[31m'); N=$(printf '\033[0m'); else B= G= Y= R= N=; fi
ok()   { printf '%s✓%s %s\n' "$G" "$N" "$1"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$1"; }
die()  { printf '%s✗%s %s\n' "$R" "$N" "$1" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  if [ -f "$LAUNCHER" ] && grep -qF "$MARK" "$LAUNCHER"; then rm -f "$LAUNCHER"; ok "removed $LAUNCHER"
  else warn "no managed launcher at $LAUNCHER"; fi
  if [ -d "$DEST/.git" ] && [ -f "$DEST/hermes_office/__main__.py" ]; then rm -rf "$DEST"; ok "removed $DEST"; fi
  echo "Left in place: ~/.hermes-office-token (access token), if it exists. Delete it yourself if you want."
  exit 0
fi

printf '%shermes-office-3d%s installer\n\n' "$B" "$N"

# 1. Python 3.9+ (the runtime is standard library only).
command -v python3 >/dev/null || die "python3 is missing. Install Python 3.9 or newer, then re-run."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "Python 3.9+ is required (found $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])'))."
ok "python3 $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])') found"

# 2. Code: this clone, or a managed one in ~/.local/share.
HERE=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ -n "$HERE" ] && [ -f "$HERE/hermes_office/__main__.py" ] && [ -d "$HERE/web" ]; then
  DEST="$HERE"
  ok "using this clone: $DEST"
elif [ -d "$DEST/.git" ]; then
  command -v git >/dev/null || die "git is missing."
  git -C "$DEST" pull --ff-only -q || die "could not update $DEST (local changes?)"
  ok "updated $DEST"
else
  command -v git >/dev/null || die "git is missing: install it (macOS: xcode-select --install), then re-run."
  [ ! -e "$DEST" ] || die "$DEST exists and is not a clone of this project: move it away first."
  mkdir -p "$(dirname "$DEST")"
  git clone -q --depth 1 "$REPO" "$DEST" || die "could not download $REPO"
  ok "downloaded to $DEST"
fi

# 3. Launcher on the PATH. It runs from the install folder so a .env there is read.
mkdir -p "$BIN"
if [ -e "$LAUNCHER" ] && ! grep -qF "$MARK" "$LAUNCHER" 2>/dev/null; then
  die "$LAUNCHER already exists and is not ours: move it away first."
fi
cat > "$LAUNCHER" <<LAUNCH
#!/bin/sh
$MARK
cd "$DEST" && exec python3 -m hermes_office "\$@"
LAUNCH
chmod +x "$LAUNCHER"
ok "installed $LAUNCHER"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH: add  export PATH=\"\$HOME/.local/bin:\$PATH\"  to your shell profile.";; esac

# 4. Optional live mode.
if [ -f "$DEST/.env" ]; then ok "found $DEST/.env (live mode configured)"
else echo "  Optional live mode: cp $DEST/.env.example $DEST/.env, then set HERMES_API_KEY (and HERMES_OFFICE_TOKEN)."; fi

printf '\n%sDone.%s Try the demo (no secrets, no Hermes needed):  hermes-office-3d --demo\n' "$B" "$N"
echo "Then open the printed URL and sign in with the token in ~/.hermes-office-token."
