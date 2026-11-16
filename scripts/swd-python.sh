#!/bin/sh
# Finds Python 3.9 or later by any of its names and starts it: the one way the plugin's hooks and
# skills start Python, on macOS, Linux and Windows (Git Bash).
#
#   sh swd-python.sh run <script> [args...]   run the script; with no Python, print a notice, exit 0
#   sh swd-python.sh check                    print the command that starts Python, or how to get it
#   sh swd-python.sh install --yes            install Python with winget, on Windows only
#
# Strict POSIX sh: it runs under dash on Ubuntu and under Git for Windows' bash in POSIX mode.
# `install` runs only after the user said yes to a skill; a hook never runs it.

NOTICE='swd: the swd plugin needs Python 3.9 or later and found none (tried python3, python and py -3). Run /swd:setup: it can install Python on Windows, or tell you the command for this system.'
MISSING='python: missing (none of python3, python or py -3 is Python 3.9 or later)'
PROBE='import sys; print("%d.%d.%d" % sys.version_info[:3]); sys.exit(sys.version_info < (3, 9))'
# The installer command is fixed text: nothing from the arguments, a project or the environment
# reaches it. It is written twice, as shown here and as run in install_python.
WINGET_LINE='winget install --exact --id Python.Python.3.13 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements'
CR=$(printf '\r')

# On Windows, `py`, `python` and `python3` from the Python install manager download and install a
# runtime, with no prompt, when none is installed, and the classic `py` launcher does when one of
# the PYLAUNCHER variables is set. Only `install --yes` installs, so no probe and no run may.
export PYTHON_MANAGER_AUTOMATIC_INSTALL=false
unset PYLAUNCHER_ALLOW_INSTALL PYLAUNCHER_ALWAYS_INSTALL

# Commands are looked for in PATH's absolute folders only. An empty or relative entry is searched
# from the current folder, which for a hook is the user's project, so a planted `python` would run.
# An empty PATH means the current folder too, hence a folder that does not exist when none is left.
rest=$PATH:
clean=
while [ -n "$rest" ]; do
    case ${rest%%:*} in /*) clean=$clean${clean:+:}${rest%%:*} ;; esac
    rest=${rest#*:}
done
PATH=${clean:-/nonexistent}

# When $1 [$2] is Python 3.9 or later, sets NAME, PY (its full path), PY_ARG ("-3" or empty) and
# VERSION. The program and its argument stay separate, so a path with spaces works.
try_python() {
    command -v "$1" >/dev/null 2>&1 || return 1
    # stdin from /dev/null keeps the hook's input for the script; the Store stub fails here
    VERSION=$("$1" ${2:+"$2"} -c "$PROBE" </dev/null 2>/dev/null) || return 1
    VERSION=${VERSION%"$CR"}  # Python on Windows ends the line with CR LF
    NAME=$1 PY=$(command -v "$1") PY_ARG=$2
}

try_names() {
    try_python python3 || try_python python || try_python py -3
}

# Sets PY, PY_ARG, VERSION and SHOWN (the command as it is typed), or returns 1.
find_python() {
    if try_names; then
        SHOWN=$NAME${PY_ARG:+ -3}
        return 0
    fi
    # On Windows a fresh install reaches PATH only in new terminals, and python.org's installer
    # leaves python off PATH: look in the per-user folders, ahead of the Store stubs.
    [ -n "${LOCALAPPDATA:-}" ] && command -v cygpath >/dev/null 2>&1 || return 1
    base=$(cygpath -u "$LOCALAPPDATA" 2>/dev/null) || return 1
    case $base in /*) ;; *) return 1 ;; esac  # a relative folder would be searched from the project
    saved_path=$PATH
    PATH=$base/Programs/Python/Launcher:$base/Programs/Python/Python313:$PATH
    try_names
    found=$?
    PATH=$saved_path
    [ "$found" -eq 0 ] || return 1
    SHOWN=$(single_quoted "$PY")${PY_ARG:+ -3}
}

single_quoted() {
    rest=$1 out=
    while :; do
        case $rest in
            *\'*) out=$out${rest%%\'*}"'\\''"; rest=${rest#*\'} ;;
            *) break ;;
        esac
    done
    printf "'%s%s'" "$out" "$rest"
}

# Sets SYSTEM, HOW (how to install Python here) and CAN (yes when swd can install it).
how_to_install() {
    CAN=no
    case $(uname -s 2>/dev/null) in
        MINGW*|MSYS*|CYGWIN*)
            SYSTEM=windows
            if command -v winget >/dev/null 2>&1; then
                HOW=$WINGET_LINE CAN=yes
            else
                HOW='by hand, from https://www.python.org/downloads/windows/'
            fi ;;
        Darwin)
            SYSTEM=macos
            if command -v brew >/dev/null 2>&1; then HOW='brew install python'; else HOW='xcode-select --install'; fi ;;
        *)
            SYSTEM=other
            if command -v apt-get >/dev/null 2>&1; then
                HOW='sudo apt-get install python3'
            elif command -v dnf >/dev/null 2>&1; then
                HOW='sudo dnf install python3'
            else
                HOW='by hand, from https://www.python.org/downloads/'
            fi ;;
    esac
}

found_line() {
    printf 'python: %s (Python %s)\n' "$SHOWN" "$VERSION"
}

install_python() {
    if find_python; then
        found_line
        echo 'nothing to install'
        exit 0
    fi
    how_to_install
    if [ "$SYSTEM" != windows ]; then
        printf '%s\ninstall: %s\n' "$MISSING" "$HOW"
        echo 'swd does not run installers on macOS or Linux: run the command above yourself, then run /swd:setup again.'
        exit 4
    fi
    if [ "$CAN" != yes ]; then
        printf '%s\ninstall: %s\n' "$MISSING" "$HOW"
        exit 5
    fi
    echo "running: $WINGET_LINE"
    winget install --exact --id Python.Python.3.13 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements </dev/null
    status=$?
    if find_python; then
        found_line
        echo 'installed: Python now runs'
        exit 0
    fi
    echo "python: still missing after winget (exit $status)"
    echo 'install: by hand, from https://www.python.org/downloads/windows/'
    exit 5
}

usage() {
    echo 'usage: sh swd-python.sh run <script> [args...] | check | install --yes' >&2
    exit 2
}

case ${1:-} in
    run)
        [ $# -ge 2 ] || usage
        shift
        if find_python; then
            exec "$PY" ${PY_ARG:+"$PY_ARG"} "$@"
        fi
        echo "$NOTICE"  # never block the prompt, command or switch the hook runs for
        exit 0 ;;
    check)
        [ $# -eq 1 ] || usage
        if find_python; then
            found_line
            exit 0
        fi
        how_to_install
        printf '%s\ninstall: %s\nswd can install it: %s\n' "$MISSING" "$HOW" "$CAN"
        exit 3 ;;
    install)
        if [ $# -ne 2 ] || [ "$2" != --yes ]; then
            echo 'usage: sh swd-python.sh install --yes' >&2
            exit 2
        fi
        install_python ;;
    *) usage ;;
esac
