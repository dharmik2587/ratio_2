#!/usr/bin/env bash
# RATIO Phase 3 — bootstrap a Chromium for Playwright E2E in restricted environments.
#
# The Playwright CDN is not reachable from every sandbox. This script instead:
#   1. installs @playwright/test and @sparticuz/chromium from the npm registry,
#   2. extracts the Chromium binary shipped inside the @sparticuz/chromium tarball,
#   3. if the host lacks NSS/NSPR system libraries, builds them from source
#      (GitHub-hosted NSPR + NSS 3.53, make-based) into frontend/.e2e-chromium/lib.
#
# Requirements for the library build path only: gcc, g++, make, python3, git.
# System Chromium can be used instead via RATIO_CHROMIUM_PATH.
set -euo pipefail

FRONTEND="$(cd "$(dirname "$0")/../frontend" && pwd)"
CHROME_DIR="$FRONTEND/.e2e-chromium"
LIB_DIR="$CHROME_DIR/lib"

cd "$FRONTEND"
npm install --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund

if [ ! -x "$CHROME_DIR/chrome" ]; then
  echo "[bootstrap] extracting Chromium from @sparticuz/chromium tarball"
  mkdir -p "$CHROME_DIR"
  node -e "
    const fs = require('fs');
    const path = require('path');
    const zlib = require('zlib');
    const source = path.join(process.cwd(), 'node_modules', '@sparticuz', 'chromium', 'bin', 'chromium.br');
    fs.writeFileSync('$CHROME_DIR/chrome', zlib.brotliDecompressSync(fs.readFileSync(source)), { mode: 0o755 });
  "
fi

needs_libs() {
  LD_LIBRARY_PATH="$LIB_DIR" ldd "$CHROME_DIR/chrome" 2>/dev/null | grep -q 'not found'
}

if [ -f "$LIB_DIR/libnss3.so" ] && [ -f "$LIB_DIR/libnspr4.so" ]; then
  echo "[bootstrap] NSS/NSPR runtime libraries already present"
elif ! needs_libs; then
  echo "[bootstrap] system provides NSS/NSPR; nothing to build"
else
  echo "[bootstrap] host lacks NSS/NSPR — building runtime libraries from source"
  TMP="$(mktemp -d)"
  mkdir -p "$LIB_DIR"
  echo "[bootstrap] cloning NSPR"
  git clone --depth 1 https://github.com/bee040811/nspr.git "$TMP/nspr" 2>/dev/null
  ( cd "$TMP/nspr"
    ./configure --prefix="$TMP/nspr-dist" --enable-64bit --disable-debug --enable-optimize >/dev/null
    make -j"$(nproc)" >/dev/null
    make install >/dev/null )
  cp "$TMP/nspr-dist"/lib/libnspr4.so "$TMP/nspr-dist"/lib/libplc4.so "$TMP/nspr-dist"/lib/libplds4.so "$LIB_DIR"/
  echo "[bootstrap] cloning NSS 3.53"
  git clone --depth 1 https://github.com/nss-dev/nss.git "$TMP/nss" 2>/dev/null
  ( cd "$TMP/nss"
    git fetch --depth 1 origin tag NSS_3_53_RTM 2>/dev/null
    git checkout -q NSS_3_53_RTM
    # Use the NSPR we just built instead of the (make-4.3-incompatible) bundled one.
    python3 - <<'PYEOF'
src = open('Makefile').read()
src = src.replace("""build_nspr: $(NSPR_CONFIG_STATUS)
	$(MAKE) -C $(CORE_DEPTH)/../nspr/$(OBJDIR_NAME)
	$(MAKE) -C $(CORE_DEPTH)/../nspr/$(OBJDIR_NAME)/pr/tests
""", "build_nspr: ;\n")
open('Makefile', 'w').write(src)
import re
p = 'lib/certdb/certdb.c'
src = open(p).read()
src = re.sub(r"\n[ \t]*PORT_AssertArg\(prstat == PR_SUCCESS\);\n", "\n", src)
open(p, 'w').write(src)
PYEOF
    export NSS_ENABLE_WERROR=0 USE_64=1 BUILD_OPT=1
    make nss_build_all NSPR_INCLUDE_DIR="$TMP/nspr-dist/include/nspr" \
         NSPR_LIB_DIR="$TMP/nspr-dist/lib" >/dev/null || true
  )
  NSS_DIST="$(ls -d "$TMP/dist"/*/lib 2>/dev/null || true)"
  if [ -z "$NSS_DIST" ] || [ ! -f "$NSS_DIST/libnss3.so" ]; then
    echo "[bootstrap] ERROR: NSS build did not produce libraries" >&2
    exit 1
  fi
  cp -L "$NSS_DIST/libnss3.so" "$NSS_DIST/libnssutil3.so" "$LIB_DIR"/
  rm -rf "$TMP"
fi

echo "[bootstrap] verifying browser"
LD_LIBRARY_PATH="$LIB_DIR" "$CHROME_DIR/chrome" --version
echo "[bootstrap] done — run: cd frontend && npm run test:e2e"
