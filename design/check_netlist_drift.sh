#!/usr/bin/env bash
# Opt-in, local netlist drift check (issue #312). Needs xschem and the PDKs;
# deliberately NOT run in CI (hygiene.yml stays PDK-free).
#
# Regenerates every committed netlist into a temp dir and diffs it against the
# committed copy after normalization (drop "**" header comments -- sch_path,
# sym_path, **.subckt -- and blank lines; real .subckt/.ends lines are kept).
#
# Usage: design/check_netlist_drift.sh [--selftest]
#   PDK_ROOT must be set (parent of ihp-sg13g2/ and ihp-sg13cmos5l/).
# Exit: 0 no drift (or only the known pin delta), 1 drift, 2 xschem/PDK
# missing, 3 orphan netlist.
#
# Known pin delta (issue #405): the committed ihp-sg13cmos5l netlists were
# generated at the archived pin (sim/pdk-sg13cmos5l.json), whose symbols do not
# emit mm_ok=1; the dev pin's do. A diff in that set consisting solely of added
# mm_ok=1 tokens is reported as "KNOWN-PIN-DELTA" (exit unchanged); the refresh
# is deferred scope (#322). Any other difference is still DRIFT.
set -u

normalize() { grep -v '^\*\*' "$1" | grep -v '^[[:space:]]*$'; }
# Remove added mm_ok=1 tokens (regenerated side only).
strip_mm_ok() { sed -E 's/[[:space:]]+mm_ok=1([[:space:]]|$)/\1/g'; }

if [ "${1:-}" = "--selftest" ]; then
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  printf '** sch_path: /a/x.sch\n**.subckt x a b\n\n.subckt x b a\nR1 a b 1k\n.ends\n' >"$t/a"
  printf '** sch_path: /other/y.sch\n\n.subckt x b a\nR1 a b 1k\n.ends\n' >"$t/b"
  printf '** sch_path: /a/x.sch\n.subckt x a b\nR1 a b 1k\n.ends\n' >"$t/c"
  diff <(normalize "$t/a") <(normalize "$t/b") >/dev/null || { echo "selftest FAIL: header churn flagged"; exit 1; }
  diff <(normalize "$t/a") <(normalize "$t/c") >/dev/null && { echo "selftest FAIL: .subckt change missed"; exit 1; }
  # Known pin delta: only added mm_ok=1 tokens -> equal after stripping.
  printf '.subckt x b a\nXM1 a b sg13_hv_pmos w=1u\nR1 a b rppd w=1u\n.ends\n' >"$t/d"
  printf '.subckt x b a\nXM1 a b sg13_hv_pmos w=1u mm_ok=1\nR1 a b rppd mm_ok=1 w=1u\n.ends\n' >"$t/e"
  printf '.subckt x b a\nXM1 a b sg13_hv_pmos w=2u mm_ok=1\nR1 a b rppd w=1u\n.ends\n' >"$t/f"
  diff <(normalize "$t/d") <(normalize "$t/e") >/dev/null && { echo "selftest FAIL: mm_ok delta not seen as a diff"; exit 1; }
  diff <(normalize "$t/d") <(normalize "$t/e" | strip_mm_ok) >/dev/null || { echo "selftest FAIL: mm_ok-only delta not classified"; exit 1; }
  diff <(normalize "$t/d") <(normalize "$t/f" | strip_mm_ok) >/dev/null && { echo "selftest FAIL: mm_ok plus other change masked"; exit 1; }
  echo "selftest OK"; exit 0
fi

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
command -v xschem >/dev/null || { echo "ERROR: xschem not found; cannot check drift (this is NOT a pass)." >&2; exit 2; }
[ -n "${PDK_ROOT:-}" ] || { echo "ERROR: PDK_ROOT unset; cannot check drift (this is NOT a pass)." >&2; exit 2; }

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
rc=0
# dir : PDK variant : rcfile
for spec in "$here:ihp-sg13g2:./xschemrc" "$here/sg13cmos5l:ihp-sg13cmos5l:../xschemrc"; do
  IFS=: read -r dir pdk rcfile <<<"$spec"
  if [ ! -d "$PDK_ROOT/$pdk" ]; then
    echo "ERROR: $PDK_ROOT/$pdk missing; cannot check ${dir#$here/} (NOT a pass)." >&2; exit 2
  fi
  for net in "$dir"/netlist/*.spice; do
    [ -e "$net" ] || continue
    base=$(basename "$net" .spice)
    if [ ! -f "$dir/$base.sch" ]; then
      echo "ORPHAN: $net has no $base.sch"; rc=3; continue
    fi
  done
  for sch in "$dir"/*.sch; do
    base=$(basename "$sch" .sch)
    [ -f "$dir/netlist/$base.spice" ] || { echo "skip: $base.sch (no committed netlist) in $dir"; continue; }
    out="$tmp/$pdk"; mkdir -p "$out"
    if ! (cd "$dir" && PDK="$pdk" xschem -n -x -q -r --rcfile "$rcfile" -o "$out" "./$base.sch") >"$tmp/log" 2>&1 \
       || [ ! -s "$out/$base.spice" ]; then
      echo "ERROR: xschem failed on $dir/$base.sch" >&2; cat "$tmp/log" >&2; exit 2
    fi
    if d=$(diff -u --label "committed/$pdk/$base.spice" --label "regenerated/$pdk/$base.spice" \
           <(normalize "$dir/netlist/$base.spice") <(normalize "$out/$base.spice")); then
      echo "ok: $pdk/$base"
    elif [ "$pdk" = ihp-sg13cmos5l ] \
         && diff -q <(normalize "$dir/netlist/$base.spice") <(normalize "$out/$base.spice" | strip_mm_ok) >/dev/null; then
      echo "KNOWN-PIN-DELTA: $pdk/$base (only added mm_ok=1; committed netlist is at the archived pin, refresh deferred to #322)"
    else
      echo "DRIFT: $pdk/$base"; echo "$d"; [ $rc -eq 0 ] && rc=1
    fi
  done
done
exit $rc
