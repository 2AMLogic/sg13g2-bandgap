# spec — porting plan + decision records

The ratified target spec table (once ratified) will live in the top-level
[`README.md`](../README.md#target-specification). Until then, this
directory holds:

```
spec/
  README.md               this file
  porting-plan.md          what carries over from gf180-bandgap and
                            sky130-bandgap, what changes and why, and the
                            SG13G2-specific device evidence behind it
  decision-records/
    TEMPLATE.md             copy this to start a new record
    NNNN-<slug>.md           one decision per record, numbered sequentially
```

See [`porting-plan.md`](porting-plan.md) for the full porting analysis and
[`decision-records/`](decision-records/) for the two decisions it records so
far (bipolar device selection, supply voltage scope). Per `CLAUDE.md`, spec
changes go through a decision record here — agents do not relax the spec to
make results pass. A record is never deleted or rewritten once ratified — a
later change supersedes it with a new record rather than editing history in
place (same append-only convention as `sim/`, see
[`sim/README.md`](../sim/README.md)).
