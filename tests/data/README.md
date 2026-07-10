# QET import fixtures — motor start/stop

These files drive **test-first** development of PanelKit's QElectroTech
importer (`integrations/qet/`, milestones Q1–Q6 in
`PanelKit_QET_Architecture.md`; working agreement in
`docs/qet/CLAUDE_QET_addendum.md`).

> **Revision note (2026-07-10).** Corrected after reconciling against genuine
> QET output — the 20 QET-authored example projects shipped with Ubuntu's
> `qelectrotech` 0.9 package (format versions 0.3–0.80; ~7,000 placed
> terminals, ~2,900 conductors). The `.qet` fixture now mirrors the verified
> 0.80-era conventions (embed:// type paths, placeholder terminal names,
> uuid/noise attributes, `manufacturer_reference`). Run
> `scripts/check_qet_fixtures.py` after touching any fixture — it re-derives
> the golden from the other two files by the documented rules.

| File | Role |
|---|---|
| `motor_start_stop.qet` | Input: a QET-style project (power + control, one folio). |
| `motor_start_stop.terminal_map.json` | Element filename → ordered pin names (see below). |
| `motor_start_stop.import.golden.json` | **The authoritative contract:** the exact PanelKit project the importer must produce (persistence format v2). |

## The circuit

A classic 3-phase motor start/stop with seal-in: incoming mains → terminal
block `X1` (points 1–3) → breaker `Q1` → contactor `K1` main poles → overload
`F1` → motor `M1` via `X1` field terminals (points 4–6). Control: `F1` NC
contact (95-96) in series with STOP `S1` (NC) and START `S2` (NO), with `K1`
aux NO (13-14) sealing in around `S2`, driving coil `A1`/`A2`. Control L/N
enter on `X1` points 7/8 (an external 24 VDC feed, matching the
`CON-3P-24VDC` coil).

Ratings are nominal fixture values, not a sizing exercise (a 25 A breaker and
16 A overload are oversized for a 4 kW ≈ 8.7 A motor) — do not "correct" them
without regenerating the golden and terminal map together.

## What the importer must do (encoded in the golden)

1. **Read elements**, taking the component `tag` from the `label` information
   field and the `part_number` from the **`manufacturer_reference`** field
   (QET's standard, UI-editable field; the custom `panelkit_pn` name used by
   earlier drafts is accepted as a legacy fallback but is not authorable in
   the QET UI).
2. **Match element types by trailing filename.** Real QET saves rewrite
   collection paths to `embed://import/...`, so the terminal map is keyed by
   the `.elmt` filename only (verified against real saves).
3. **Resolve terminals → pins via the terminal map.** QET stores no usable
   terminal names — real placed terminals carry `name` absent, `""`, or the
   placeholder `"_"` (verified; treat all three as unnamed). The i-th
   `<terminal>` of a placed element (document order) maps to `pin_names[i]`
   for that element's filename.
4. **Reconstruct nets by conductor walking, per folio.** Build a graph whose
   nodes are terminal ids and whose edges are `<conductor>` entries; each
   connected component is one net. Terminal ids are unique **per folio only**
   (verified — real multi-folio projects reuse ids across folios), so the
   graph is per-`<diagram>`; v1 imports single-folio projects and fails
   loudly otherwise. The three-pin nets here (`NET_0013/14/15` motor feeds,
   `NET_0007/0012` control nodes) are formed from **two conductors each** —
   the case this fixture exercises.
5. **Name nets deterministically.** All conductors in this fixture have
   `num=""`, so every net gets a synthetic name: order nets by ascending
   minimum terminal id — **numeric comparison, not string** (string order
   would shuffle `NET_0007` onward) — then number `NET_0001…`. Real projects
   populate `num` about half the time (verified); when present it becomes the
   net name, with conflicts resolved per the addendum (smallest value +
   warning). Not exercised by this fixture.
6. **Emit components with `placement: null`.** Import sets *connectivity
   only*; geometry is authored later in PanelKit. `wires`, `surfaces`,
   `ducts`, `bundles`, `harnesses` are all empty on import. Null placement is
   a base-model amendment — see the addendum for the full downstream
   contract.
7. **Parse tolerantly.** The fixture deliberately carries the noise real
   saves have (element `uuid`/`z`/`freezeLabel`, terminal
   `name="_" number="_" nameHidden="0"`, extra conductor attributes); the
   importer reads only what it needs and ignores the rest.
8. **Serialize stably:** the golden is in PanelKit persistence format v2 —
   keys sorted, pins within a net sorted by `[tag, pin]` **as strings** (so
   `"14"` precedes `"A1"`, as in `NET_0007`). Note the deliberate contrast:
   pins sort as strings, net ordering is numeric.

## Acceptance (Q4)

`import-qet motor_start_stop.qet --terminal-map motor_start_stop.terminal_map.json`
must produce a project **structurally equal** to the golden: load both the
golden and the importer's output through `json_store.load` (with the QET
parts library from Q3) and compare the resulting `Project` objects. Do not
compare serialized text produced by any other serializer. 7 components,
17 nets.

## Honest caveats

- **The `.qet` is hand-built, then reconciled against real QET examples**
  (format 0.3–0.80) — not exported from QET itself. The conventions that
  matter for import are verified; exact nesting of a v0.9/v0.100 save should
  still be confirmed by drawing this circuit in QET and saving (the
  reconciliation checklist is in the addendum). The **golden JSON is the
  stable contract** regardless of how the `.qet` is produced — reconcile
  differences in the parser and the `.qet`, never the golden.
- **The seven part numbers must exist in a library at import time.** The
  terminal map supplies pin *names* only; Q3 ships matching PanelKit part
  JSONs (pin positions, sizes) alongside the QET symbol collection so
  imported projects validate and can be placed/routed.
- **Terminal-map dependency is fundamental, not optional.** Without the map
  (or an equivalent matched-symbol convention) pins cannot be resolved.
- **Regenerating for real:** draw this circuit in QET (0.9 via
  `apt install qelectrotech`, or 0.100) using a PanelKit-matched symbol set,
  save, and run the importer against it. Diff against the golden; reconcile
  differences in the parser, not the golden.
