# sg13cmos5l-closed-loop-startup

PVT-cornered testbench co-simulating `design/sg13cmos5l/bandgap_core.sch` +
`bandgap_amp.sch` + `bandgap_startup.sch` (issue #65, phase 2/4 of the
SG13CMOS5L port, issue #63). This is the SG13CMOS5L analogue of
[`sim/closed-loop-startup/`](../closed-loop-startup/README.md) (the SG13G2
precedent) and the formal, PVT-cornered counterpart to
`design/sg13cmos5l/README.md`'s own single-nominal-corner informal
closed-loop check (issue #68).

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
                                         # AND a sibling ihp-sg13g2/ -- see
                                         # sim/pdk-sg13cmos5l.json
                                         # "sibling_checkout_requirement"
export PDK=ihp-sg13cmos5l
sim/sg13cmos5l-closed-loop-startup/run_pvt_sweep.sh
```

Requires ngspice on `PATH`. This PDK ships its OSDI device models prebuilt --
see `sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`.

## What this claims

Wired exactly as `design/sg13cmos5l/bandgap_top.sch` specifies (`core.fb <-
amp.out`, `core.sns1 -> amp.in_n`, `core.sns2 -> amp.in_p`, `startup` shares
`sns1` and `fb` with the core), with `vdd` itself ramped `0 -> VDD` over
200 us and held to 2 ms, the assembled block **self-starts and settles to a
closed-loop operating point** across the full temperature x supply x
pnpMPA/MOS/resistor-process-corner PVT grid:

1. **Startup released**: `v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA`.
2. **Loop closed**: `|sns1 - sns2| <= 20 mV` -- the amplifier's whole job is
   forcing these two nodes equal.
3. **Not railed**: `fb` sits strictly inside `(vss, vdd)`, at least 50 mV from
   either rail -- confirms a real negative-feedback equilibrium rather than a
   polarity-bug saturation to one supply.

This is closed-loop infrastructure/plumbing evidence for issue #65, **not** a
claim against any ratified spec row (no ratified SG13CMOS5L accuracy target
exists yet -- `spec/porting-plan-sg13cmos5l.md`).

## What's different from the SG13G2 precedent

- **Core topology is reversed** -- grounded-collector `pnpMPA` legs instead
  of grounded-emitter `npn13G2` legs. See
  `sim/sg13cmos5l-core-open-loop-bias/README.md` for the full account; the
  wiring into the amplifier and startup circuit is unaffected, since both of
  those consume `sns1`/`sns2`/`fb` as plain node voltages regardless of which
  terminal of the bipolar device they come from.
- **`cornerPNP.lib` replaces `cornerHBT.lib`** in the `.lib` section list,
  same `PNP_SECTION_OF` map (and `sf`/`fs` -> `typ` fallback) as
  `sim/sg13cmos5l-core-open-loop-bias`.
- **No OSDI compile step**: this PDK ships `.osdi` models prebuilt (see
  `sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`).
- **Supply grid is unchanged** (`{2.97, 3.30, 3.63}` V) -- see
  `sim/pdk-sg13cmos5l.json` `"supply_rails"`.
- Everything else -- the `rshunt=1e9 gmin=1e-9` convergence aids, the `vdd`
  PWL ramp shape, the three pass criteria and their thresholds, the
  `|| true`-guarded `.measure` parsing for non-convergent marginal corners --
  is identical to `sim/closed-loop-startup`, reused verbatim because none of
  it is PDK-specific.

## Cross-check against the informal single-corner result (issue #68)

`design/sg13cmos5l/README.md`'s own informal check at `typ`/`mos_tt`/`res_typ`,
27 degC, `vdd=3.3V` reported `|sns1-sns2| = 0.233 mV`, `fb = 2.49710 V`,
`det = 4.18836 mV`, `i(XMKFB) = 2.497 nA` -- this experiment's own `typ`
corner at the same temperature/supply point reproduces those results (see the
record's own CSV row for the exact re-run values), confirming this formal
testbench's fixture matches the informal check's fixture rather than
introducing a new discrepancy.

## Not attempted

Mismatch/Monte Carlo, AC/loop-stability (phase margin -- no compensation
capacitor exists in `bandgap_amp.sch` yet), DRC/LVS, layout. No MoM-cap-
dependent measurement exists in this testbench (none of the three DUTs
instantiate a capacitor) -- when a future phase adds a compensation/filter
cap, its spec row must be marked `insufficient-evidence` per issue #65's own
acceptance criteria, since MoM caps carry no corner/mismatch spread in this
PDK's models (`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`).
