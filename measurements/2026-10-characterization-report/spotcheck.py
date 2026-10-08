#!/usr/bin/env python3
"""Re-derive every number quoted in README.md from the committed sim/ CSVs.

    python3 -I measurements/2026-10-characterization-report/spotcheck.py

Read-only: opens committed CSVs, prints one labelled line per quoted figure.
Nothing is simulated. The output at the audited commit is reproduced in the
report's "Spot-check output" section.
"""
import csv
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "sim"


def rows(rel):
    with open(SIM / rel, newline="") as fh:
        return list(csv.DictReader(fh))


def f(r, k):
    return float(r[k])


def rng(vals):
    return min(vals), max(vals)


def say(label, text):
    print(f"{label}: {text}")


# --- Output reference, untrimmed, schematic, trim-bearing (current) ---------
p = "closed-loop-vref-pvt/records/20261001-085908-e5507b2"
r = rows(p + ".csv")
ok = [x for x in r if x["status"] == "PASS"]
v = [f(x, "vref_3ms_v") for x in ok]
lo, hi = rng(v)
nom = [x for x in r if x["corner_label"] == "typ" and x["temp_c"] == "27" and x["vdd_v"] == "3.30"][0]
say("vref-pvt sch trim-bearing", f"{len(ok)}/{len(r)} PASS; vref {lo:.5f}..{hi:.5f} V; "
    f"vs 1.050 V: {100*(lo/1.05-1):+.2f}%..{100*(hi/1.05-1):+.2f}%; "
    f"nominal typ/27C/3.30V {f(nom,'vref_3ms_v'):.5f} V ({100*(f(nom,'vref_3ms_v')/1.05-1):+.3f}%); "
    f"max settle delta {max(f(x,'vref_settle_delta_v') for x in ok):.2g} V")
t = rows(p + "-tc.csv")
tc = [f(x, "tc_ppm_per_c") for x in t]
say("vref-pvt sch trim-bearing endpoint TC", f"{len(t)} groups; {min(tc):.1f}..{max(tc):.1f} ppm/C; "
    f"max |TC| {max(abs(c) for c in tc):.1f}; groups < 50: {sum(abs(c)<50 for c in tc)}; "
    f"groups < 20: {sum(abs(c)<20 for c in tc)}")

# --- same, PEX trim-bearing: vref_op_v of the psrr-pex record -----------------
p = "closed-loop-psrr-pex/records/20261004-030337-5553d523"
r = rows(p + ".csv")
ok = [x for x in r if x["status"] == "PASS"]
v = [f(x, "vref_op_v") for x in ok]
say("psrr-pex vref_op (PEX trim-bearing, 27C/DC op only)", f"{len(ok)}/{len(r)} PASS; vref_op {min(v):.5f}..{max(v):.5f} V")
d = [f(x, "psrr_dc_db") for x in ok]
w = min(ok, key=lambda x: f(x, "psrr_dc_db"))
say("PSRR@DC PEX trim-bearing", f"{min(d):.3f}..{max(d):.3f} dB; >60 dB: {sum(c>60 for c in d)}/{len(d)}; "
    f">70 dB: {sum(c>70 for c in d)}/{len(d)}; worst {f(w,'psrr_dc_db'):.4f} dB at "
    f"{w['corner_label']}/{w['temp_c']}C/{w['vdd_v']}V")
nd = sorted(f(x, "psrr_dc_db") for x in ok)
say("PSRR@DC PEX trim-bearing, 2nd/3rd worst", f"{nd[1]:.3f}, {nd[2]:.3f} dB")
mins = [f(x, "psrr_min_db") for x in ok]
say("PSRR above-DC min (PEX trim-bearing)", f"psrr_min_db {min(mins):.2f}..{max(mins):.2f} dB (HF notch, not the DC row)")

# --- PSRR schematic trim-bearing --------------------------------------------
r = rows("closed-loop-psrr/records/20261001-085737-e5507b2.csv")
ok = [x for x in r if x["status"] == "PASS"]
d = [f(x, "psrr_dc_db") for x in ok]
w = min(ok, key=lambda x: f(x, "psrr_dc_db"))
say("PSRR@DC sch trim-bearing", f"{min(d):.3f}..{max(d):.3f} dB; >60 dB: {sum(c>60 for c in d)}/{len(d)}; "
    f">70 dB: {sum(c>70 for c in d)}/{len(d)}; worst {f(w,'psrr_dc_db'):.4f} dB at "
    f"{w['corner_label']}/{w['temp_c']}C/{w['vdd_v']}V")

sup = set()
for rel in ("closed-loop-vref-pvt/records/20261001-085908-e5507b2.csv", "closed-loop-iq/records/20261001-092257-4fe07ea.csv",
            "closed-loop-psrr/records/20261001-085737-e5507b2.csv", "closed-loop-startup/records/20261001-083332-e5507b2.csv",
            "closed-loop-psrr-pex/records/20261004-030337-5553d523.csv"):
    sup |= {x["vdd_v"] for x in rows(rel)}
say("Supply grid actually swept by the current records", sorted(sup))

# --- Iq ---------------------------------------------------------------------
r = rows("closed-loop-iq/records/20261001-092257-4fe07ea.csv")
ok = [x for x in r if x["status"] == "PASS"]
q = [f(x, "iq_avg_a") * 1e6 for x in ok]
w = max(ok, key=lambda x: f(x, "iq_avg_a"))
say("Iq sch trim-bearing", f"{len(ok)}/{len(r)} PASS; {min(q):.2f}..{max(q):.2f} uA; <50 uA: "
    f"{sum(c<50 for c in q)}/{len(q)}; <20 uA: {sum(c<20 for c in q)}/{len(q)}; worst "
    f"{w['corner_label']}/{w['temp_c']}C/{w['vdd_v']}V; margin to 50 uA {100*(1-max(q)/50):.1f}%; "
    f"max settle delta {max(f(x,'iq_settle_delta_a') for x in ok):.2g} A")

# --- Startup ----------------------------------------------------------------
r = rows("closed-loop-startup/records/20261001-083332-e5507b2.csv")
say("startup sch trim-bearing", f"{sum(x['status']=='PASS' for x in r)}/{len(r)} PASS")
r = rows("startup-time-to-release/records/20261001-085905-e5507b2.csv")
rt = [x["release_time_us"] for x in r if x["status"] == "PASS"]
say("startup time-to-release sch trim-bearing", f"{len(rt)}/{len(r)} PASS; release_time_us values {sorted(set(rt))}; "
    f"max {max(float(c) for c in rt):.0f} us (ladder step 100 us)")
r = rows("startup-trip-point-pex/records/20260905-033740-fe97115.csv")
say("startup trip point PEX (2026-09-05)", f"{sum(x['status']=='PASS' for x in r)}/{len(r)} PASS")

# --- Trim row ---------------------------------------------------------------
r = rows("trim-coverage/records/20260930-195507-9530863-analysis.csv")
up = [f(x, "up_span_pct") for x in r]
dn = [f(x, "down_span_pct") for x in r]
ls = [f(x, "lsb_pct_of_target") for x in r]
wd = [f(x, "worst_weight_dev_pct") for x in r]
say("trim-coverage", f"{sum(x['group_status']=='PASS' for x in r)}/{len(r)} groups PASS; range up "
    f"+{min(up):.2f}..+{max(up):.2f}%, down -{min(dn):.2f}..-{max(dn):.2f}% (worst-case "
    f"+{min(up):.2f}/-{min(dn):.2f}); LSB {min(ls):.4f}..{max(ls):.4f} %/step; worst binary-weight "
    f"deviation {max(wd):.4f}%; monotonic in {sum(x['monotonic']=='yes' for x in r)}/{len(r)}")
r = rows("trim-coverage/records/20260930-195507-9530863.csv")
say("trim-coverage points", f"{sum(x['status']=='PASS' for x in r)}/{len(r)} PASS")

# --- Trimmed accuracy: trim-domain MC ---------------------------------------
dg = rows("closed-loop-vref-trim-mc/records/20260930-232155-affdefe-draws.csv")
dig = rows("closed-loop-vref-trim-mc/records/20260930-232155-affdefe.csv")
for pt in ("nominal", "bcs", "wcs", "negctrl"):
    d = [x for x in dg if x["point"] == pt]
    okd = [x for x in d if x["verify_status"] == "PASS"]
    m = [f(x, "max_dev_pct") for x in okd]
    say(f"trim-MC {pt}", f"N={len(d)} draws, {len(okd)} converged ({len(d)-len(okd)} excluded); "
        f"within +/-0.5% over -40..125C: {100*sum(int(x['within_0p5']) for x in okd)/len(okd):.1f}%; "
        f"3*sigma(max_dev) {3*st.stdev(m):.3f}%; worst draw {max(m):.2f}%; seeds "
        f"{d[0]['seed']}..{d[-1]['seed']}")
for x in dig:
    say(f"trim-MC digest {x['corner_label']}", f"status {x['status']}, n_pass {x['n_pass']}/{x['n_draws']}, "
        f"frac_within_0p5 {float(x['frac_within_0p5_pct']):.2f}%, 3sigma {float(x['three_sigma_max_dev_pct']):.3f}%")
nom = [x for x in dg if x["point"] == "nominal" and x["verify_status"] == "PASS"]
d27 = [abs(f(x, "dev_27c_pct")) for x in nom]
say("trim-MC nominal at the 27C trim point", f"max |dev_27c| {max(d27):.3f}%; draws with |dev_27c|<=0.5%: "
    f"{sum(c<=0.5 for c in d27)}/{len(d27)}")
# the nominal (draw 0 is a mismatch draw, not the mismatch-free die); mismatch-free die drift:
bt = rows("closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv")
bt.sort(key=lambda x: x["corner_label"])
# --- Temperature coefficient, trim-bearing box method ------------------------
near = [x for x in bt if x["trim_code"] in ("127", "128", "129")]
c128 = [x for x in near if x["trim_code"] == "128"]
complete = [x for x in near if x["n_pass"] == x["n_grid"]]
def box(xs):
    return [f(x, "box_tc_ppm_per_c") for x in xs]
say("box TC trim-bearing, code 128", f"{len(c128)} groups; {min(box(c128)):.1f}..{max(box(c128)):.1f} ppm/C; "
    f"< 20: {sum(c<20 for c in box(c128))}; < 50: {sum(c<50 for c in box(c128))}")
w = max(c128, key=lambda x: f(x, "box_tc_ppm_per_c"))
say("box TC trim-bearing, code 128 worst", f"{w['corner_label']}/{w['vdd_v']}V {f(w,'box_tc_ppm_per_c'):.3f}")
say("box TC trim-bearing, codes 127..129", f"{len(near)} groups; {min(box(near)):.1f}..{max(box(near)):.1f} ppm/C; "
    f"< 50: {sum(c<50 for c in box(near))}/{len(near)}; < 20: {sum(c<20 for c in box(near))}/{len(near)}")
w = max(near, key=lambda x: f(x, "box_tc_ppm_per_c"))
say("box TC trim-bearing worst near-band", f"{w['corner_label']}/{w['vdd_v']}V {f(w,'box_tc_ppm_per_c'):.3f} "
    f"(n_pass {w['n_pass']}/{w['n_grid']})")
inc = [x for x in near if x["n_pass"] != x["n_grid"]]
say("box TC groups with excluded points", f"{len(inc)} of {len(near)} near-band groups have n_pass<n_grid "
    f"({', '.join(x['corner_label']+'/'+x['vdd_v']+'V:'+x['n_pass']+'/'+x['n_grid'] for x in inc)})")
say("box TC complete groups only", f"{len(complete)} groups; max {max(box(complete)):.3f}")
# endpoint-TC on pre-trim PEX/schematic records (history)
for rel, lab in (("closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa-tc.csv", "PEX pre-trim endpoint TC (STALE)"),):
    t = [f(x, "tc_ppm_per_c") for x in rows(rel)]
    say(lab, f"{min(t):.1f}..{max(t):.1f} ppm/C over {len(t)} groups")
for rel, lab in (("closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc-boxtc.csv", "sch pre-trim box TC (STALE)"),
                 ("closed-loop-vref-pvt-pex-boxtc/records/20260921-195122-77820fc-boxtc.csv", "PEX pre-trim box TC (STALE)")):
    b = rows(rel)
    k = "box_tc_ppm_per_c"
    w = max(b, key=lambda x: f(x, k))
    say(lab, f"{len(b)} groups; max {f(w,k):.1f} ppm/C at {w['corner_label']}/{w['vdd_v']}V (n_pass {w['n_pass']}/{w['n_grid']})")
b = rows("closed-loop-vref-boxtc-pretrim-aidsfree/records/20261002-125922-d770c09-boxtc.csv")
say("pre-trim aids-free A/B", f"{len(b)} groups; header {list(b[0].keys())[:6]}")
for x in b:
    print("   ", {k: x[k] for k in list(x.keys())[:12]})

# --- Untrimmed MC (STALE: pre-trim DUT) --------------------------------------
dg = rows("closed-loop-vref-mc/records/20260909-232418-c9b83ab-draws.csv")
dig = rows("closed-loop-vref-mc/records/20260909-232418-c9b83ab.csv")
for x in dig:
    say(f"untrimmed MC digest {x['corner_label']} (STALE)", f"{x['temp_c']}C n_pass {x['n_pass']}/{x['n_draws']}, mean "
        f"{float(x['mean_vref_v']):.6f} V, 3sigma/mean {float(x['three_sigma_over_mean_pct']):.2f}%, "
        f"within 1%: {100*float(x['frac_within_1pct']):.1f}%, within 0.5%: {100*float(x['frac_within_0p5pct']):.1f}%")
d = [f(x, "vref_v") for x in dg if x["point"] == "nominal" and x["status"] == "PASS"]
say("untrimmed MC nominal recomputed from draws (STALE)", f"N={len(d)} mean {st.mean(d):.6f} sigma {st.stdev(d):.6f} "
    f"3sigma/mean {100*3*st.stdev(d)/st.mean(d):.2f}%")
dd = [f(x, "vref_v") for x in dg if x["point"] == "nominal" and x["status"] == "PASS"]
tot = max(float(x["three_sigma_over_mean_pct"]) * float(x["mean_vref_v"]) / 1.05
          + abs(float(x["mean_vref_v"]) / 1.05 - 1) * 100
          for x in dig if "mismatch" in x["corner_label"])
say("untrimmed worst-case 3sigma total vs 1.050 V (STALE; DR-0011's 15.3% sum)", f"{tot:.2f}% vs the +/-16% line")
say("untrimmed MC +/-16% band around 1.050 V (STALE)", f"draws inside [0.882, 1.218] V: "
    f"{sum(0.882<=c<=1.218 for c in dd)}/{len(dd)}")
r = rows("closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.csv")
v = [f(x, "vref_3ms_v") for x in r if x["status"] == "PASS"]
nm = [x for x in r if x["corner_label"] == "typ" and x["temp_c"] == "27" and x["vdd_v"] == "3.30"][0]
say("PEX pre-trim vref grid (STALE)", f"{len(v)} PASS; {min(v):.5f}..{max(v):.5f} V; nominal {f(nm,'vref_3ms_v'):.5f} V")

# --- Loop gain supplementary --------------------------------------------------
r = rows("loop-gain-phase-margin/records/20261003-180919-2addad0.csv")
ok = [x for x in r if x["status"] == "PASS" and x["quality"] == "ok"]
say("loop-gain (supplementary, not a spec row)", f"{sum(x['status']=='PASS' for x in r)}/{len(r)} PASS, "
    f"{len(ok)} quality=ok rows")
pm = [f(x, "phase_margin_deg") for x in r if x["phase_margin_deg"] not in ("", "NA", "nan")]
if pm:
    say("loop-gain phase margin", f"{len(pm)} rows with a crossover; min {min(pm):.1f} deg")
