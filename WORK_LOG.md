# Work Log

Chronological record of completed work in this repository, maintained by the Guide role.

Entries are grouped by date, newest first. Each entry references a merged PR or closed issue.

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-24

- **PR #664**: sim: source shared verdict constants in boxtc-pretrim-aidsfree run_one_point
- **Issue #660** (closed): Shell bench run_one_point.sh keeps a 5th unguarded copy of the four closed-loop verdict constants
- **PR #686**: chore(layout): remove the superseded one-point PEX probe
- **PR #684**: refactor(sim): dedupe gen_probe_deck onto shared harness and collapse resize variants
- **Issue #682** (closed): Deduplicate gen_probe_deck.py onto shared sim/harness modules and collapse per-instance _sub resize tables
- **Issue #656** (closed): Remove superseded one-point PEX probe (layout/bandgap_core/probe): its #275 stopgap condition is met

### 2026-11-23

- **PR #685**: test(sim): fail loudly when a harness source escapes the shell-closure regex
- **PR #683**: docs(sim): describe the pre-open refusal in the preserved-companion tests
- **PR #679**: refactor(sim): refuse empty TC companion derivations before opening output
- **PR #678**: fix: resolve nested-quote source paths in runner_shell_closure
- **PR #674**: fix(sim): make the schematic-DUT render source and record spec explicit flags
- **PR #665**: sim: drop logic-free psrr/zout summary wrappers, invoke db_summary_common.awk directly
- **Issue #681** (closed): TC companion preservation tests still document the removed write-and-restore mechanism
- **Issue #680** (closed): runner_shell_closure: line-start anchor is an unchecked assumption about how runners source harness scripts
- **Issue #675** (closed): Remove write-and-restore handling from both TC companion commands
- **Issue #670** (closed): Shared schematic-DUT helpers read DUT_TEMPLATE/RECORD_SPEC from the environment without binding them to the submission identity
- **Issue #663** (closed): EnricherIdentityCoverageTests' shell closure misses pex_runner.sh (source-line regex)
- **Issue #460** (closed): Remove two logic-free awk wrappers (zout_summary.awk, psrr_summary.awk) left behind by the klt sim conversion
- **PR #669**: fix(sim): state measured probe-fleet bounds in psrr attribution record
- **Issue #667** (closed): sim(psrr): tighten five claim-precision items in the #631 attribution bench and DR-0017
- **PR #673**: docs: correct klayout-tools#6974 status in closed-loop MC README
- **PR #651**: refactor: share the schematic-DUT setup and record mint across the six klt sim wrappers
- **PR #640**: Pass the untrimmed 3-sigma gate at N=1200: re-run the vref mismatch MC, re-mint the yield evidence, rotate the item-8 report
- **Issue #672** (closed): Declare item-6's negative control once a PyPI release carries the klayout-tools#6974 CSV-control fix (and correct the 'still unlanded' note)
- **Issue #671** (closed): Judge docs-only fast path is permanently NOT ELIGIBLE on gh 2.102.0 (unsupported `baseRepository` field)
- **Issue #650** (closed): Deduplicate schematic-DUT setup across 6 run_klt_sim.sh wrappers and share schematic_ac_main in pex_ac_runner.sh
- **Issue #635** (closed): Untrimmed MC 3-sigma gate fails at the 125 C corners (sigma LB 2.8845 / 2.8632 vs 3): size and run the follow-up campaign
- **PR #639**: sim(psrr): attribute the DC-PSRR miss at bcs/125C/3.63V and grid-verify the p12-w2 input-pair candidate (45/45 above 60 dB)
- **Issue #631** (closed): design: PSRR @ DC misses the > 60 dB row at bcs/125 C/3.63 V (59.685 dB schematic); attribute the limit and propose a bounded fix
- **PR #658**: docs(sim): document runner-function call shape and msense failure paths
- **PR #662**: fix: hash enrich_pvt_report.py in affected runners' submission identity
- **PR #659**: refactor: consolidate the closed-loop verdict constants, 3-criteria check and recount into enrich_pvt_report
- **PR #655**: refactor: dedupe klt_trim_axis.py onto the shared sim/harness modules
- **PR #649**: manifests: point the item-8 bullet at the pinned report and CI-check it
- **Issue #654** (closed): Document read_msense_width caller attribution and parse failures in shared runners
- **Issue #661** (closed): Submission identity does not hash enrich_pvt_report.py, which five enrichers now depend on
- **Issue #657** (closed): Consolidate closed-loop verdict constants, 3-criteria check, report recount, and dead/redundant code across sim/harness enrichers
- **Issue #652** (closed): Deduplicate klt_trim_axis.py onto shared sim/harness modules (CORNER_SECTIONS, seed_deck, klt_sim_evidence, provision default)
- **Issue #647** (closed): manifests/README.md item-8 paragraph links a superseded report: heading cites the pinned rotation, body still points at 2026-11-18

### 2026-11-22

- **PR #645**: Cite the four klt sim corner-matrix envelopes for T1 item 5, grading each row's bound in the run itself
- **PR #644**: test: fold TC golden append-only check into one byte-exact regeneration per fixture
- **Issue #629** (closed): T1 item 5 (corner verification): cite the klt sim corner-matrix envelopes per spec row and declare the row set, so the item grades on evidence instead of no_evidence
- **Issue #643** (closed): Compare TC companion fixtures byte-for-byte in one regeneration per fixture
- **PR #637**: fix: draw pnpMPA base-ring contacts by widening the wall to 0.30 um
- **Issue #633** (closed): sg13cmos5l-bandgap_top: pnpMPA base rings carry zero contacts (draw_pnpmpa cont_array underflow at w=1u l=2u) — the base tie does not exist as drawn

### 2026-11-21

- **PR #636**: Mint klt yield evidence for the untrimmed Output-reference MC line (T1 item 6)
- **Issue #630** (closed): T1 item 6 (Monte Carlo): produce and cite a klt yield report for the untrimmed Output-reference line, with a real negative control and the statistical row set declared
- **Issue #628** (closed): Rebase PR #383 (runset recognition layers, #380 + #387) onto current main: resolve 38 conflicts, regenerate layout, re-mint evidence, re-run the three PEX benches

### 2026-11-19

- **PR #596**: docs: document merge-time staleness hazard for layout evidence
- **Issue #587** (closed): Layout evidence can go stale against a concurrently-merged GDS change, and PR CI never re-checks it

### 2026-11-18

- **PR #624**: fix: end build-osdi.sh help at header terminator
- **Issue #623** (closed): build-osdi.sh -h prints 6 lines past the end of the header; sim/README.md has a stray short line
- **Issue #622** (closed): Post-merge: file the build-osdi.sh re-vendor follow-up for the 9 remaining consumer repos
- **PR #621**: build-osdi.sh: embed toolchain pins as JSON and add --print-pins
- **Issue #620** (closed): build-osdi.sh: carry the pins as embedded JSON and print them, so consumers stop restating them
- **PR #617**: ci: report hygiene's base-diff gates on merge_group commits (merge queue step 1)
- **PR #616**: fix: correct klu-retime README log claims and un-ignore measurements logs
- **Issue #615** (closed): measurements/2026-11-klu-retime README promises per-run ngspice.log files that .gitignore's *.log rule silently dropped
- **Issue #614** (closed): Merge queue: add the merge_group trigger to the required-check workflow(s)
- **PR #613**: sim: adopt the klu direct solver on both supply benches (measured 1.44x/1.36x hot-corner wins)
- **PR #612**: fix(layout): refresh bandgap_top leaf_inputs.json to the post-#572 core GDS hash
- **PR #611**: refactor: hoist shared git capture and waiver-file preamble into _ci_common
- **Issue #610** (closed): Dedupe .github/scripts: _git and the waiver-file loader are copied between check_report_regression and check_evidence_formats
- **PR #608**: fix: report a malformed leaf sidecar entry instead of crashing the evidence checker
- **Issue #607** (closed): main is red: bandgap_top leaf_inputs.json leaf binding stale after #588's hygiene run (non-waived STALE)
- **Issue #595** (closed): check_evidence_formats: malformed leaf_inputs.json entry crashes with KeyError instead of the intended failure report
- **PR #589**: fix(layout): put fold_plan's inter-leg gap on the 5 nm manufacturing grid
- **Issue #573** (closed): layout: cont.ongrid.1 x4 in bandgap_startup under the current sg13g2 deck
- **Issue #518** (closed): sim: re-time closed-loop-iq / closed-loop-startup under KLU on an uncontended host (#489 left the number undetermined)

- **PR #593**: layout: bind assembly tops to the leaf GDS hashes they embed via leaf_inputs.json
- **Issue #588** (closed): layout: bind bandgap_top.gds (and CMOS5L top) to the leaf GDS hashes it embedded — a stale leaf can hide in a committed top for weeks
- **PR #605**: fix: fail closed on non-integer per-class counts in report regression guard
- **PR #604**: fix(layout): cite #557, not #552, in bandgap_top's DRC waiver comment
- **PR #602**: docs: sync item-8 citation to the 2026-11-18 report and bandgap_top LVS prose to the committed 8-finding mint
- **PR #600**: ci: guard DRC/LVS re-mints against outcome regressions vs the merge base
- **PR #591**: fix(layout): land Metal1 on draw_npn13g2's base-contact Cont rows
- **Issue #601** (closed): check_report_regression: a non-integer per-class count is dropped silently, so the per-class comparison can read as a pass
- **Issue #598** (closed): Docs drift in layout/README.md and manifests/README.md: wrong klayout version on the DRC/ERC mints, stale characterization-report date and top-LVS finding count
- **Issue #594** (closed): Evidence ladder has no regression guard: a re-minted DRC/LVS report that gets worse passes every checker
- **Issue #584** (closed): layout: bandgap_top/drc_waivers.json _comment cites #552 (unrelated) where it means #557
- **Issue #572** (closed): layout: metal1.enclosing.cont.1 x18 in bandgap_core under the require_containment sg13g2 deck
- **PR #599**: docs: disclose the 0.8.0 deck's Offgrid/containment scope narrowing in DR-0016
- **PR #592**: test: pin _sg13g2_rppd_ohms at R1's (2u, 37.2u) in the lvs_reference self-test
- **PR #586**: layout: re-mint all committed layout evidence under the klt 0.8.0 pin (#561 step 2)
- **PR #583**: fix: enforce b=0/m=1 precondition of lvs_reference's formula resistor paths
- **PR #576**: fix(layout): raise TAP_NWELL_MARGIN_UM to the deck's 0.24um nwell.enclosing.nactiv.1 floor
- **Issue #597** (closed): DR-0016: disclose that the pinned 0.8.0 deck cannot see the containment rule families #572/#573 are filed against
- **Issue #590** (closed): lvs_reference self-test: _sg13g2_rppd_ohms is the one formula helper whose value is not pinned
- **Issue #582** (closed): lvs_reference.py: the PDK symbol-formula resistor paths silently assume b=0 and m=1
- **Issue #579** (closed): Rebase PR #576 (#571 tap-margin fix) onto post-#574 main: layout regen + evidence re-mint
- **Issue #571** (closed): layout: nwell.enclosing.nactiv.1 (amp 5, core 6, top 11) under the require_containment sg13g2 deck
- **Issue #561** (closed): Evidence backlog: 20 committed layout reports predate the DR-0016 evidence standard (klt 0.8.0)
- **PR #580**: layout: derive SG13G2 rppd reference values from the PDK's own rppd.sym formula (issue #561 step 1)
- **PR #578**: fix(layout): drop double-applied CORE_DX in bandgap_top vref column x
- **Issue #577** (closed): layout: bandgap_top's vref column double-applies CORE_DX (latent; harmless only while CORE_DX == 0)
- **PR #574**: fix(layout): enclose core/top Via1 landings in Metal2 at the deck's fixed 0.19 um
- **Issue #557** (closed): layout: remaining via1 end-cap/size defects in bandgap_core, bandgap_startup, bandgap_top under the current sg13g2 deck

### 2026-11-17

- **PR #569**: docs: correct rhigh trace narrative (schematic path, unmatched split)
- **PR #566**: layout: value SG13G2 rhigh reference from the PDK symbol formula, trace the 0.8.0 deck r delta
- **Issue #568** (closed): docs: two precision fixes in the #563 rhigh trace narrative (wrong schematic path, unmatched-finding attribution)
- **Issue #563** (closed): trace: bandgap_top rhigh X3_RPU `r` delta +4.2% (1999501.7 Ω layout vs 1919368.0 Ω reference) — the 1019th LVS error-severity finding
- **PR #565**: docs: root README status block matches committed DRC/LVS reports after the DR-0016 re-mint
- **PR #560**: evidence: re-mint bandgap_top LVS under pinned klt 0.8.0; add DR-0016 evidence standard
- **PR #559**: fix(layout): enclose bandgap_amp Via1 landings in Metal2 at the deck's fixed 0.19 um
- **Issue #564** (closed): docs: root README status block attributes bandgap_top's LVS mismatch to the 3 NPN13G2 devices — stale after the DR-0016 re-mint
- **Issue #558** (closed): tool drift: top-level LVS findings explode 10/4 -> 1023/1019 under klt 0.9.3 deck; signoff manifest ROTTED on main
- **Issue #556** (closed): layout: bandgap_amp has 12 Via1 shapes half outside Metal2 (metal2.enclosing.via1.1)
- **PR #554**: chore(loom): resync installed Loom to v0.19.1306
- **PR #550**: chore(sim): remove closed-loop-vref-pvt run_pvt_sweep.sh, superseded by run_klt_sim.sh twin
- **PR #546**: ci: gate characterization spot-check output blocks on live re-run
- **Issue #519** (closed): Remove closed-loop-vref-pvt run_pvt_sweep.sh: superseded by the new run_klt_sim.sh twin
- **Issue #516** (closed): No gate re-derives the characterization reports' committed "Spot-check output" blocks
- **PR #552**: fix(harness): companions remove the refused CSV instead of leaving it header-only
- **PR #551**: fix: derive boxtc-trim mint block's shared-grid literals from CORNER_LABELS/VDDS
- **PR #548**: fix: derive boxtc-trim mint block's grid cardinality from TEMPS
- **PR #547**: docs: source the 100 °C fleet-timing claim to the committed record
- **Issue #549** (closed): boxtc-trim mint block still restates two shared-grid cardinalities as literals ("5 transient validation points", the {typ,bcs,wcs,sf,fs} x {2.97,3.30,3.63} V grid)
- **Issue #544** (closed): Trim bench mint block still restates the TEMPS cardinality as "8-temperature grid" (sixth instance, missed by #530's table)
- **Issue #536** (closed): TC companions leave a header-only CSV on disk when main() refuses (#510 residual)
- **Issue #515** (closed): closed-loop-vref-pvt-boxtc README quotes a per-100 °C-point timing range the committed record cannot source
- **PR #543**: fix(sim): derive boxtc-trim record grid prose from array constants
- **PR #542**: docs: document batch PDK-root precedence in trim-axis env header; reflow harness README
- **Issue #530** (closed): The trim bench's array-valued constants (NEAR_CODES, FAR_CODES, FAR_CORNERS, FAR_VDDS, TEMPS count) are still restated as record prose
- **Issue #524** (closed): Docs nit: name the generic KLT_SIM_BATCH_PDK_ROOT in run_klt_trim_axis.sh's Environment header; re-wrap sim/harness/README.md:634

### 2026-11-16

- **PR #540**: refactor: hoist seed_row and fill_deck into seed_deck.py
- **PR #513**: chore(loom): resync installed Loom to v0.19.1302
- **Issue #487** (closed): render_deck() in the two MC harnesses carries 11 more byte-identical lines, and the 3-line half already has a factored helper in trim_coverage_klt
- **PR #538**: chore(sim): delete startup-time-to-release run_pvt_sweep.sh, superseded by run_klt_sim.sh
- **Issue #520** (closed): Remove startup-time-to-release run_pvt_sweep.sh: superseded by its run_klt_sim.sh twin

- **PR #535**: fix(harness): TC companions refuse an empty derivation instead of exiting 0
- **Issue #510** (closed): sim/harness: a TC companion that derives zero rows should be loud, not a header-only CSV
- **PR #529**: fix(sim): derive trim bench WORST_NEAR span label and headroom prose from constants
- **Issue #527** (closed): Two more box-TC record-prose literals in the trim bench sit outside #517's fix (headroom pct, WORST_NEAR span)
- **PR #526**: fix(sim): derive box-TC trim record span prose from span constants
- **Issue #517** (closed): The box span's prose restatements (165) sit outside #474's tripwire, including one that lands in minted evidence
- **PR #511**: docs: record cited_envelopes() full-consumption contract in its docstring
- **Issue #500** (closed): cited_envelopes()'s docstring does not record the full-consumption contract its generator conversion introduced
- **Issue #273** (closed): Finish the #264 refresh: closed-loop-vref-mc (1800 draws) and closed-loop-vref-pvt-boxtc (120 transient points)
- **PR #523**: refactor: route the standalone batch submitters through klt_sim_batch_defaults
- **PR #521**: refactor: share schematic_vref_main in the vref PEX runner
- **Issue #512** (closed): Dedupe sim wrapper leftovers after #465: endpoint-method TC companion and schematic_vref_main are each copy-pasted across two benches
- **Issue #503** (closed): run_klt_trim_axis.sh keeps a third copy of the batch provision-script default
- **PR #508**: evidence: trim-bearing 120-point box-TC record, retire the #273 waiver
- **PR #504**: test: tripwire the trim bench's awk box-TC copy to boxtc_companion
- **PR #501**: docs: record measured KLU-vs-SPARSE solve times for closed-loop-iq and closed-loop-startup
- **PR #494**: refactor: hoist the duplicated klt-sim runner preamble into one shared file
- **PR #482**: feat(sim): klt sim wrapper for startup-time-to-release, with a ladder enricher mode
- **Issue #489** (closed): Consider the KLU direct solver on the sibling klt sim benches that share the boxtc DUT
- **Issue #481** (closed): Hoist the duplicated klt-sim runner preamble shared by pex_runner.sh and cmos5l_runner.sh
- **Issue #474** (closed): A third box-method TC implementation survives #465: closed-loop-vref-boxtc-trim's awk copy
- **Issue #468** (closed): sim: add a klt sim wrapper for startup-time-to-release (Startup row)
- **Issue #402** (closed): sim: refresh closed-loop-vref-pvt-boxtc (120 points) via concurrent klt sim shard submission (Part of #273)
- **PR #509**: refactor: share the endpoint-method TC companion via sim/harness/tc_companion.py
- **PR #498**: refactor(sim): hoist SEED_FIELDS and load_seeds into one shared seed_deck module
- **PR #490**: refactor: drop last hand-rolled MSENSE parse; de-enumerate sim/lib caller headers
- **PR #499**: fix: yield cited_envelopes() lazily so walk diagnostics interleave with each caller's tail
- **Issue #496** (closed): sim/harness: factor the endpoint-method TC companion into a shared helper (and fix its vdd_v formatting)
- **Issue #486** (closed): Hoist the triplicated nodeset-seed loader and SEED_FIELDS token map into one harness module
- **Issue #473** (closed): Drop the last hand-rolled MSENSE-width parse and fix sim/lib/msense_width.sh's stale caller list
- **Issue #493** (closed): _ci_common.cited_envelopes() batches its diagnostics ahead of each caller's tail, reordering multi-problem failure output

### 2026-11-15

- **PR #495**: pex: share one vref DUT body template between the pex and pex-boxtc benches
- **PR #491**: sim: add the klt sim wrapper for closed-loop-vref-pvt
- **PR #488**: sim: adopt KLU direct solver on closed-loop-vref-pvt-boxtc (3643s -> 211s hot corner)
- **PR #492**: refactor: dedupe the manifest-to-envelope citation resolver into _ci_common
- **PR #479**: refactor(ci): fold two checkers into _ci_common's shared scaffolding
- **PR #476**: refactor: give the MC harness family one copy of its corner-section mapping
- **PR #485**: docs(layout): one complete SG13G2 build recipe, unique section headings
- **Issue #472** (closed): Dedupe the PEX vref DUT wrapper: closed_loop_vref_pvt_pex_boxtc.body.spice.tmpl is byte-identical to its sibling, and the harness already has the BODY_TEMPLATE override
- **Issue #467** (closed): sim: add a klt sim wrapper for closed-loop-vref-pvt (Output-reference nominal row)
- **Issue #469** (closed): sim: get the box-TC 100 C corner to solve inside the batch job limit (unblocks #402)
- **Issue #477** (closed): Dedupe .github/scripts: the two dependency checkers each carry the same manifest-to-envelope citation resolver
- **Issue #475** (closed): Dedupe .github/scripts: check_artifact_manifests.py re-grows _ci_common's Report, resolve_root and ls-files reader
- **Issue #478** (closed): layout/README.md: consolidate the three colliding "Reproducing" sections — neither SG13G2 recipe regenerates all four cells
- **Issue #463** (closed): Dedupe the Monte Carlo klt-sim harnesses: PDK corner-section maps, sections(), make_ctx() and load_seeds() re-typed instead of imported
- **PR #497**: docs: align README status, maturity ladder and measurements/ line with committed evidence
- **PR #505**: refactor: extract shared spotcheck bodies into measurements/lib/spotcheck_common.py
- **PR #506**: test: pin the shared PEX body-template contract in SetDispatchWiringTests
- **Issue #470** (closed): docs: bring the README status and maturity-ladder lines in line with the signoff verdict
- **Issue #484** (closed): Deduplicate the characterization reports' spotcheck.py: 186 of 201 lines are identical in all four copies
- **Issue #502** (closed): Harness tests do not pin the shared PEX body-template contract (#472 / PR #495)

### 2026-11-14

- **PR #471**: refactor(sim): one home for the box-method TC derivation
- **PR #466**: docs: roadmap as of 2026-11-13
- **PR #462**: sim: gate every grid dispatch through one anchor-check implementation
- **Issue #465** (closed): Dedupe the box-method TC companion: pex_record_companion() is byte-identical in two experiments, with a shared runner already sourced by both
- **Issue #458** (closed): Consolidate six copies of the --sanity anchor gate into one tested harness helper

### 2026-11-13

- **PR #461**: docs: drop seven converted experiments from sim/README.md unconverted list
- **PR #457**: sim: submit batch campaign shards concurrently via klt --batch-set
- **PR #456**: sim: drop two uncalled awk helpers from pvt_sed_common.sh
- **PR #455**: chore(sim): remove legacy run_trim_coverage.sh hand-launched ngspice loop
- **PR #453**: sim: record closed-loop-psrr 45-point batch grid
- **Issue #459** (closed): Remove seven converted experiments from the 'Still unconverted' list in sim/README.md
- **Issue #454** (closed): Remove dead is_new_max() and latest_records_csv() from sim/lib/pvt_sed_common.sh
- **Issue #452** (closed): Remove legacy run_trim_coverage.sh: superseded by run_klt_sim.sh
- **Issue #415** (closed): sim: add klt sim wrapper for schematic closed-loop-psrr (Part of #412)

### 2026-11-12

- **PR #451**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-10

- **PR #450**: chore(sim): remove legacy run_mc.sh and run_trim_mc.sh ngspice loops
- **Issue #448** (closed): Remove legacy run_mc.sh / run_trim_mc.sh: superseded by run_klt_sim.sh
- **Issue #371** (closed): Live --batch run of the shared PEX runner driver (sim/harness/pex_runner.sh)

### 2026-11-07

- **PR #449**: Bump Repo Skills 0.25.1 -> 0.25.10

### 2026-11-06

- **PR #447**: ci: run orphaned harness self-tests in hygiene and guard against new orphans
- **PR #446**: chore(sim): delete 9 legacy run_pvt_sweep.sh superseded by run_klt_sim.sh
- **PR #445**: chore(sim): remove 4 SG13CMOS5L legacy run_pvt_sweep.sh runners
- **Issue #444** (closed): ci: run the three orphaned sim/harness self-tests in hygiene.yml, and guard against new orphans
- **Issue #443** (closed): Remove 4 SG13CMOS5L legacy run_pvt_sweep.sh runners (split from #438)
- **Issue #441** (closed): Classify the sg13cmos5l bandgap_amp netlist port-order drift (committed vs schematic)
- **Issue #438** (closed): Remove 13 legacy run_pvt_sweep.sh runners superseded by run_klt_sim.sh

### 2026-11-04

- **PR #439**: feat(sim): run closed-loop-vref-mc on the klt sim fleet with a trim-bearing record
- **Issue #403** (closed): sim: closed-loop-vref-mc klt sim monte_carlo seeding design and 1800-draw refresh (Part of #273)
- **Issue #299** (closed): signoff: bind T1 items 9 and 10 (and re-bind item 1) to audited artifacts (klayout-tools#2718 landed)

### 2026-11-01

- **PR #437**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-30

- **PR #434**: measurements: re-mint trim records on the fleet and add the November characterization report
- **PR #433**: fix: write PEX batch .lib cards under the submitting PDK root
- **PR #425**: sim: run the trim-domain mismatch Monte Carlo on klt sim decks
- **Issue #432** (closed): pex_runner.sh: stop emitting absolute /opt/pdk .lib paths in batch requests (klt 0.8.x refuses them)
- **Issue #427** (closed): Re-mint trim-coverage and trim-mc records and publish a new dated characterization report
- **Issue #423** (closed): sim: add klt sim decks wrapper for closed-loop-vref-trim-mc (split from #416)

### 2026-10-29

- **Issue #416** (closed): sim: add klt sim wrappers for the Trim benches (trim-mc, trim-coverage) (Part of #412)
- **PR #422**: sim: add klt sim wrapper and fleet record for the trim-coverage bench
- **Issue #242** (closed): README: embed the fleet burndown chart (one line)
- **Issue #426** (closed): Remove legacy run_pvt_sweep.sh loops in the 13 experiments that already have run_klt_sim.sh
- **PR #428**: docs: describe run_pvt_sweep.sh as a point-definition reference, not an entry point

### 2026-10-28

- **PR #421**: sim: add klt sim wrapper for schematic closed-loop-psrr
- **PR #418**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup
- **Issue #4** (closed): Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)
- **PR #417**: feat: add SG13G2 bandgap_top ERC evidence and cite it for T1 item 11
- **Issue #411** (closed): T1 item 11 (power delivery): commit a klt erc supply spec and report for the SG13G2 bandgap_top instead of citing the SG13CMOS5L port's ERC

### 2026-10-27

- **PR #409**: ci: pin klayout-tools to PyPI 0.8.0 and regenerate signoff verdict
- **Issue #408** (closed): Bump klayout-tools pin 7ee09483b748 → 0.8.0
- **PR #406**: docs: classify archived-pin mm_ok netlist delta in drift check
- **Issue #405** (closed): SG13CMOS5L committed netlists drift from schematics at the dev PDK pin

### 2026-10-25

- **PR #400**: refactor(sim): remove uncalled helpers from enrich_ac_report
- **Issue #399** (closed): Remove dead helpers _interp_log and _fmt_vdd from enrich_ac_report.py
- **PR #398**: feat(sim): convert closed-loop-vref-pvt-boxtc to the klt sim fleet harness

### 2026-10-24

- **Issue #385** (closed): Remove dead riser 'bridge' machinery in sg13cmos5l-bandgap_top generate.py

### 2026-10-23

- **PR #393**: docs(sim): list all 18 experiments without run_klt_sim.sh as unconverted
- **Issue #389** (closed): sim/README: list the 6 other manifest-less experiments with non-run_pvt_sweep runners
- **PR #388**: ci(sim): fail manifest-less evidence records dated on/after DR-0015
- **Issue #386** (closed): Follow-on from PR #382: convert legacy corners/-writing sim runners to the artifact store
- **PR #391**: fix(sim): make PEX klt-sim record step work cold; add partial item-9 audit log
- **Issue #310** (closed): signoff: execute the deferred cold-start testbench audit for T1 item 9
- **PR #382**: feat(sim): store new klt-sim evidence in the artifact store, commit manifests

### 2026-10-21

- **PR #365**: Bump Repo Skills 0.24.3 -> 0.24.7
- **Issue #374** (closed): Condense layout/README.md: resolved-blocker history and triplicated Reproducing sections
- **PR #375**: docs: condense resolved-blocker history in layout/README.md
- **PR #369**: refactor(sim): share one driver across the five PEX run_klt_sim.sh runners
- **Issue #366** (closed): Consolidate five near-identical sim run_klt_sim.sh runners into a shared driver
- **PR #368**: ci: pin hygiene signoff-manifest Python to 3.14
- **Issue #367** (closed): CI: hygiene/signoff-manifest fails building klayout wheel on Python 3.15 (red main)

### 2026-10-18

- **PR #361**: refactor: route remaining PEX batch runners through pex_merge_shards
- **Issue #360** (closed): Consolidate PEX klt-sim batch runners: zout-pex duplicates psrr-pex, three bypass pex_merge_call.sh
- **PR #353**: feat(lvs): grade bandgap_top with the PDK LVS runset for T1 items 4 and 11
- **Issue #352** (closed): layout: close T1 items 4 and 11 with a klayout-runset LVS report (PDK runset recognizes NPN13G2)

### 2026-10-17

- **PR #357**: refactor(ci): single-source path containment and sha256 pin check in _ci_common
- **Issue #356** (closed): Consolidate duplicated sha256-pin validation in CI evidence checkers

### 2026-10-16

- **PR #350**: Bump Repo Skills 0.24.1 -> 0.24.3

### 2026-10-15

- **PR #347**: Bump Repo Skills 0.19.5 -> 0.24.1

### 2026-10-13

- **PR #346**: sim: convert the four SG13CMOS5L experiments to the klt sim harness (#337)
- **Issue #337** (closed): sim: convert the four SG13CMOS5L experiments to the klt sim harness (Part of #322)
- **PR #344**: ci: hoist duplicated checker scaffolding into _ci_common
- **Issue #342** (closed): Simplify CI checkers: hoist duplicated manifest discovery, report printing and sha256: wrapper into _ci_common
- **PR #343**: docs(sim): index five missing experiments, enforce index completeness
- **Issue #341** (closed): docs: add the five unindexed sim/ experiments to sim/README.md and enforce index completeness
- **PR #340**: sim: reject unresolved local include closures before minting snapshots
- **Issue #333** (closed): sim: reject unresolved local include closures before minting snapshots
- **PR #338**: sim: bind resumed batch reports to the exact submitted inputs
- **Issue #332** (closed): sim: bind resumed batch reports to the exact submitted inputs
- **PR #334**: sim: repair PEX batch callers missing the mandatory expected-grid arguments
- **Issue #331** (closed): sim: repair PEX batch callers missing the mandatory expected-grid arguments

### 2026-10-12

- **PR #330**: sim: enforce append-only staged publication in the evidence adapter
- **Issue #328** (closed): sim: enforce append-only staged publication in the evidence adapter
- **PR #329**: sim: reject incomplete and malformed batch shard grids before publishing evidence
- **Issue #327** (closed): sim: reject incomplete and malformed batch shard grids before publishing evidence
- **PR #326**: ci: detect stale inputs behind the active T1 design-source audit
- **Issue #324** (closed): ci: detect stale inputs behind the active T1 design-source audit
- **PR #323**: docs: re-stamp SG13CMOS5L target pin to IHP-Open-PDK dev f7bca326 (Refs #322)
- **Issue #325** (closed): Guard blocks read-only rg search patterns in Codex

### 2026-10-09

- **PR #316**: ci: detect dependency drift in the active characterization report (#315)
- **Issue #315** (closed): ci: detect dependency drift in the active characterization summary
- **PR #314**: design: opt-in netlist drift check (#312)
- **Issue #312** (closed): design: add a netlist-vs-schematic drift check and fix the regen docs (trim missing, author paths embedded)
- **PR #311**: sim: bind PEX simulation records to their consumed extraction hashes
- **Issue #309** (closed): sim: bind PEX simulation records to their consumed extraction hashes

### 2026-10-08

- **PR #307**: measurements: October characterization report bound to T1 item 8 (#300)
- **Issue #300** (closed): measurements: refresh the aggregated characterization report against the current spec and trim-bearing core, and wrap it for T1 item 8

- **PR #306**: signoff: bind T1 items 1 and 10 to audited artifacts, bump klt pin to 3a75c3ae (#299)
- **PR #305**: docs(readme): Trim-row disposition now tracked in #303
- **PR #301**: ci: run solve-quality and harness-transformer self-tests in hygiene
- **PR #296**: chore: pin tracker-state-comment helper as repo-owned (#295)
- **Issue #265** (closed): Trimmed-line disposition: DR-0011's +/-0.5% does not hold on #229's aids-free trim-domain MC evidence
- **Issue #297** (closed): Run the loop-gain solve-quality test in hygiene CI and add harness self-tests
- **Issue #295** (closed): Orphan helper .loom/scripts/tracker-state-comment.sh: upstream it or pin it

### 2026-10-04

- **PR #293**: sim(pex): re-run three of the five PEX grids through the klt-sim batch bridge (part of #278)

### 2026-10-03

- **PR #288**: spec(0014): keep the 1-point 27 °C Trim row explicitly (no hot insertion, no CTAT knob)
- **PR #290**: sim(loop-gain): trim-code axis of phase margin; 36.3 deg is a corrupted AC solve, accept and disclose (#271)
- **PR #291**: sim(loop-gain): solve-quality gate and guarded 45-point record (#289)
- **PR #292**: sim(tools): PEX netlist-body generator for bandgap_core (part of #278)
- **Issue #289** (closed): loop-gain bench: a single AC sweep can return a numerically corrupted solve that PASSes (36.3 deg / 43.9 deg were artifacts); add a solve-quality guard
- **Issue #285** (closed): Trim row: should the ratified 1-point 27 °C trim become 2-point (room+hot) with the CTAT knob? It is the only measured path to ±0.5%
- **Issue #271** (closed): Trim ladder costs real loop phase margin at wcs/125C/2.97V (36.3 deg vs 88.5 deg pre-trim)

### 2026-10-02

- **PR #281**: docs(sim/harness): disclose the .meas 6-s.f. precision ceiling and accept it
- **PR #283**: docs: attribute the ±0.5% trimmed budget to DR-0011 in boxtc-trim README
- **PR #284**: sim(269): aids-free pre-trim box-TC A/B — the ladder, not the aids, drives the <20 ppm/°C stretch miss
- **PR #286**: sim(267)+spec(0013): measure every candidate second-trim knob's column, and decline the knob under the ratified 1-point Trim row
- **PR #287**: feat: run the klt sim probe on the batch fleet (--batch)
- **Issue #282** (closed): sim/closed-loop-vref-boxtc-trim/README.md attributes the ±0.5% budget to DR-0010 in one line and DR-0011 in another
- **Issue #280** (closed): sim/harness: the klt sim path records one fewer significant figure than run_pvt_sweep.sh, undisclosed
- **Issue #277** (closed): Infra: the EDA batch fleet image carries no ihp-sg13g2 PDK (and no OSDI build step), so klt sim cannot run this repo's corner grids
- **Issue #269** (closed): TC row: the trim-bearing, aids-free core reads 20.2-45.7 ppm/C box TC - target still met, <20 ppm/C stretch is not
- **Issue #267** (closed): Second trim degree of freedom: the 1-point R1 trim converts offset into TC at a measured 0.058%/code, which is what sets the trimmed line

### 2026-10-01

- **PR #266**: feat: trim network for the core's R1/R2 divider (DR-0011 Trim row) + evidence
- **PR #274**: test(sim): refresh 9 schematic-DUT experiments against the trim-bearing core
- **PR #276**: layout: re-draw the summing resistor as #229's trim ladder, re-run DRC/LVS/PEX
- **PR #279**: sim: settle the corner-grid harness (klt sim) and the D2 mask-option disposition (#275)
- **Issue #275** (closed): Re-run the five PEX experiments against the trim-bearing extraction (#272's scope item 3/4) — needs a corner-grid harness this host may run
- **Issue #272** (closed): Re-layout and re-extract the block against the trim-bearing core, then refresh the 5 PEX experiments
- **Issue #264** (closed): Refresh sim/ evidence against the trim-bearing core netlist (post-#229)
- **Issue #229** (closed): Design the trim network obligated by the re-cast Output-reference row (DR-0009: range >= +/-15%, <= 0.25%/step, 1-point @ 27C)

### 2026-09-30

- **PR #230**: ratification: re-cast the Output-reference row (DR-0010)
- **PR #263**: spec: renumber duplicate decision record 0010 -> 0011
- **Issue #262** (closed): spec: duplicate decision-record number 0010 on main (hygiene CI failing since PR #230 merge)
- **Issue #231** (closed): Apply the two ratification keys to PR #230 (DR-0009, Output-reference re-cast) — non-author
- **Issue #221** (closed): Output-reference row: decide its disposition (re-target vs. defend ±1% untrimmed) — both ratification keys escalated it

### 2026-09-29

- **PR #259**: chore: resync installed Loom surfaces (--force past obsolete local edits)
- **PR #261**: Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers
- **Issue #260** (closed): Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers

### 2026-09-27

- **PR #251**: docs(layout): condense SG13CMOS5L resolved-issue narrative in README to pointers
- **PR #254**: docs(layout): re-derive the #174 LVS section from the current 14-finding report
- **PR #256**: docs: fix false "no underpass needed" claim for bandgap_startup
- **PR #257**: docs(layout): re-derive SG13CMOS5L cause-4 pfet/well half and net_count from committed evidence
- **Issue #255** (closed): docs(layout): SG13CMOS5L cause-4 item still says PMOS bodies are unbiased; committed reports say vdd (plus stale net_count)
- **Issue #253** (closed): docs(layout): two stale "no underpass needed" claims for sg13cmos5l-bandgap_startup
- **Issue #252** (closed): docs(layout): #174 LVS section quotes 22 findings; committed sg13cmos5l-bandgap_top report says 14
- **Issue #250** (closed): docs: condense SG13CMOS5L half of layout/README.md — closed-issue narrative duplicated in generate.py docstrings, with stale LVS counts (follow-up to #189)

### 2026-09-26

- **PR #249**: Add pinned-comment convention for tracker issues at the addComment cap
- **Issue #248** (closed): Issue #4 hit GitHub's 2500-comment hard cap: addComment now permanently disabled

