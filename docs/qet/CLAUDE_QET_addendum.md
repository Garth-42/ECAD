# CLAUDE.md — Addendum: QET importer extension (milestones Q1–Q6)

> Append this section to the working agreement in `CLAUDE.md`. Everything in the
> base `CLAUDE.md` still applies unchanged — the work loop, the commands, and the
> core guardrails (determinism, "views never mutate the model," minimal
> dependencies, fail loudly, keep tests green). This addendum adds what's
> specific to the QElectroTech-fronted repositioning in
> `PanelKit_QET_Architecture.md`.
>
> **Revision note (2026-07-10).** This version corrects the original addendum
> after reconciling its claims against genuine QET output: the 20 QET-authored
> example projects shipped with the Ubuntu `qelectrotech` 0.9 package
> (~7,000 placed terminals, ~2,900 conductors across format versions 0.3–0.80).
> Claims marked *(verified)* below were checked against those files;
> corrections to the original text are marked *(corrected)*.

## What changed about the goal

PanelKit is now a **headless automation engine behind QElectroTech**, not a
standalone ECAD tool. QET owns the schematic and the netlist; PanelKit owns the
computed physical build (geometry, routing, lengths, cut lists) and the
automated derivation of documents. Build the QET importer as milestones
**Q1–Q6** on top of the existing M1–M10 code. Do not regenerate existing
modules.

## New prime directives (in addition to the base ones)

1. **Do not reinvest in schematic drawing.** `views/svg_schematic.py` is
   **deprecated to an optional fallback** — QET produces the schematic now.
   Don't add features to it; don't let it grow.
2. **The importer sets connectivity ONLY — never geometry.** Imported
   components get `placement: null`; `surfaces`/`ducts`/`wires` stay empty.
   Placement and routing are PanelKit-authored steps that happen *after*
   import. See "Null placement is a base-model amendment" below — this is not
   free.
3. **Merge, don't overwrite, on re-import.** See "Merge semantics" below —
   the original one-paragraph rule under-specified net identity, which is
   where re-import actually loses user data.
4. **Treat real `.qet` files as the schema authority.** Target QET stable
   **v0.100**; the parser must tolerate format versions **0.3–0.100** (the
   bundled real examples span 0.3–0.80, and Ubuntu 24.04 ships QET 0.9 —
   which is what CI can install). When the parser and a hand-built fixture
   disagree with a real QET save, fix the parser and the fixture — **never
   the golden JSON** (see "Fixtures & the golden contract").

## Facts about QET (verified against real saves)

- **Terminal "names" exist but are never meaningful** *(corrected)*. The
  original claim was "terminals carry empty `name` attributes." Real files
  show three states: `name` absent (0.3-era), `name=""`, or — in every
  0.80-era placed terminal — the placeholder `name="_" number="_"
  nameHidden="0"`. No real file carries a usable pin name. The parser must
  treat absent, `""`, and `"_"` all as *unnamed*; pin resolution **must** go
  through the terminal map (element type → ordered pin names). Ship a
  PanelKit-matched QET symbol collection so this mapping is reliable.
- **Element `type` paths are rewritten on save** *(new, verified)*. A project
  embeds its collection: placed elements reference
  `embed://import/<path>/<file>.elmt`, not the authoring-time
  `user/...` path. Terminal-map keys are therefore matched on the **trailing
  filename** (e.g. `breaker_3p.elmt`), never the full path.
- **Terminal ids are unique per folio only** *(new, verified)*. Conductors
  reference integer terminal ids (`terminal1`/`terminal2`) that restart in
  each `<diagram>`; `industrial.qet` has 88 id collisions across folios.
  Build the conductor graph **per diagram**. **v1 scope: single-folio
  projects** — if a project has more than one `<diagram>` containing
  elements, fail loudly with a clear message (cross-folio nets use
  folio-reference symbols and are a later milestone).
- **Nets are reconstructed, not read.** QET is diagram-centric with no clean
  netlist. Build a graph of terminal ids joined by conductors; each connected
  component is one net. Multi-conductor nets (3+ pins) are the case that
  breaks naive implementations.
- **Conductor `num` is populated about half the time** *(corrected)*. The
  original claim was "conductors usually have `num=""`". Across the real
  examples: 1,284 non-empty vs 1,511 empty. Named nets are a first-class
  path, and one electrical net can span conductors with *different* `num`
  values, so the rule is:
  1. Collect the distinct non-empty `num` values in a net's conductors.
  2. Exactly one distinct value → it becomes the net name.
  3. More than one → use the lexicographically smallest and emit a warning
     Finding naming the conflict.
  4. None → synthetic name (below).
- **Synthetic net naming is deterministic.** Order nets by ascending minimum
  terminal id — **compared numerically, not as strings** (string comparison
  puts `"20" < "3"` and demonstrably reorders the fixture's nets) — then
  number `NET_0001…` in that order.
- **Parse tolerantly** *(new, verified)*. Real placed elements carry `uuid`,
  `z`, `prefix`, `freezeLabel`, …; real conductors carry ~25 attributes
  (`formula`, `cable`, `bus`, colors, text layout, …). The importer reads
  only what it needs (`type`, terminals, information fields;
  `terminal1`/`terminal2`/`num`) and ignores everything else without
  complaint.
- **Part number field: `manufacturer_reference` first** *(corrected)*. QET's
  element-information dictionary is a fixed set (`label`, `formula`,
  `comment`, `manufacturer`, `manufacturer_reference`, `designation`,
  `function`, `location`, … — `manufacturer_reference` is present in the QET
  0.9 binary and is user-editable in the element dialog). A custom
  `panelkit_pn` field is **not** authorable from the QET UI. The importer
  reads the part number from `manufacturer_reference`, falling back to
  `panelkit_pn` for legacy files; the component tag comes from `label`.

## Null placement is a base-model amendment (not an importer detail)

`Component.placement` is currently a required, validated `Placement`. Making
it optional touches core modules; do it deliberately, in one commit, with this
contract:

- `Component.placement: Placement | None` (default stays required-in-spirit:
  only the importer creates `None`).
- `world_pin_position` on an unplaced component → raise with a clear
  "component X1 is not placed" message (fail loudly, never guess).
- New validation rule `unplaced_component` (error) — fires per unplaced
  component; `panelkit route`, clearance checking, and `svg_wiring` refuse to
  run while any component in use is unplaced (surface the Finding, exit
  non-zero).
- Both persistence backends (`json_store`, `sqlite_store`) round-trip
  `placement: null`; loading pre-existing files is unaffected.
- `resolve_wires` still works on unplaced projects (connectivity is
  placement-independent) so `netlist`/`connections`/`bom`/`terminals` all run
  straight after import.

## Merge semantics (Q5 — the load-bearing milestone)

Re-importing an edited schematic must preserve PanelKit-side work. `merge` is
the default mode; `replace` is an explicit escape hatch.

**Components — keyed by `tag`:**
- Existing tag → update `part_number` (warn if changed), **keep placement and
  `surface_id`**.
- New tag → add with `placement: null`.
- Disappeared tag → keep the component but emit a `stale_component` warning
  Finding; never silently delete (an explicit `--prune` flag may remove them).

**Nets — matched by pin-set, not by name** *(new — this was the gap)*.
Synthetic `NET_xxxx` names are ordinal and shuffle whenever the schematic is
edited, so net names must not be used as merge identity. For each incoming
net, find the existing net with the **largest pin-set overlap** (ties broken
by smallest existing id; zero overlap = no match):
- Matched → the incoming net keeps its new id/name but **inherits
  `Net.properties`** (gauge, color, `load_a`, …) from the matched existing
  net.
- Unmatched incoming → added fresh, empty properties.
- Unmatched existing → dropped (its connectivity no longer exists in the
  schematic), with a `stale_net` warning listing any properties that were
  discarded.

**Wires, surfaces, ducts, bundles, harnesses:** `wires` are always cleared on
merge (they are derived; re-run resolve/route). `surfaces` and `ducts` are
untouched. `bundles`/`harnesses` are kept, but any `wire_ids` they reference
are cleared with a warning (wire ids are regenerated by resolve); harness
`component_tags` referencing pruned components produce warnings.

The Q5 test asserts: placements/ducts survive; net properties survive a
renumbering edit; nothing is silently deleted.

## The loop for Q1–Q6 (same cadence as the base loop)

Build in order; keep all M1–M10 tests green throughout:
`Q1 parse → Q2 netlist (conductor walking) → Q3 mapping + matched symbol set +
matching part JSONs → Q4 import + golden-file test → Q5 merge
(placement/property-preserving) → Q6 one-shot build + docs`. Each milestone
ends with its tests passing before the next.

## Fixtures & the golden contract

The fixtures live under `tests/data/` (`motor_start_stop.qet`,
`motor_start_stop.terminal_map.json`, `motor_start_stop.import.golden.json`)
and are test-first; `tests/data/README.md` describes them.
`scripts/check_qet_fixtures.py` re-derives the golden from the other two by
the documented rules — run it after touching any fixture.

- **`…import.golden.json` is the authoritative contract** for Q4: 7 components
  with null placement, 17 nets, stable ordering, pins within a net sorted by
  `[tag, pin]` **as strings** (so `"14"` precedes `"A1"`) — note the contrast
  with *numeric* net ordering above; both comparisons are intentional.
- The golden is written in **PanelKit persistence format v2**
  (`format_version: 2`, the same shape `json_store` emits, with
  `placement: null`). "Matches the golden" means: load both the golden and
  the importer's output through `json_store.load` (with the QET parts
  library) and compare the resulting `Project`s **structurally** — never diff
  serialized text against it with a different serializer.
- If parser output diverges from the golden, the parser is wrong — never edit
  the golden to pass. The `.qet` is hand-built to mirror real QET (and has
  been reconciled against the real 0.3–0.80 examples); re-verify against a
  real v0.9/v0.100 save of the same circuit when one is available, fixing
  parser + `.qet` fixture as needed while the golden stays fixed.

## Parts for imported projects

The golden's part numbers (`BRK-3P-25A`, `CON-3P-24VDC`, `OL-3P-16A`,
`MOT-3PH-4KW`, `PB-NC-RED`, `PB-NO-GRN`, `TB-STRIP-8`) exist nowhere today.
Q3 ships them as a matched pair:

- the QET **symbol collection** (`.elmt` files whose terminal order defines
  the terminal map), and
- the PanelKit **part JSONs** (same part numbers, with pin `local_pos` and
  `size`) under a `library/data/` addition, so imported projects pass
  `unknown_part` validation and are placeable/routable without manual work.

An import that references a part number missing from the library fails loudly
at load, exactly like every other unknown-part path.

## Reconciliation checklist (run against a real QET save of the fixture circuit)

When someone draws the fixture circuit in real QET (0.9 or 0.100) and saves:

1. Placed-element `type` uses `embed://import/...` — terminal-map basename
   matching resolves it.
2. `<terminal>` order inside placed elements matches the `.elmt` definition
   order (the map's contract).
3. Terminal `name`/`number` are `_`/empty — treated as unnamed.
4. Conductors carry `terminal1`/`terminal2` integer ids scoped to the folio.
5. `manufacturer_reference` and `label` info fields survive the save with the
   values typed into the element dialog.
6. Importer output equals the golden (structural comparison).

## Dependencies & boundaries

- The importer uses **stdlib `xml.etree`** — no new dependency (`lxml` only
  if a measured need appears, and then scoped to the importer so core runs
  without it).
- The importer reads QET's **open file format**; it does **not** link or
  vendor QET's GPL code. Keep that boundary clean.

## Definition of done for the extension

- Q4 golden import matches exactly (structural comparison, defined above).
- Re-import in `merge` mode preserves placements, ducts, **and net
  properties** across a schematic edit that renumbers nets (the Q5 test).
- `panelkit build` runs the full downstream pipeline (resolve → route →
  wiring diagram → BOM → terminal plan → optional WireViz) with real routed
  lengths.
- All base M1–M10 tests still pass.
- `scripts/check_qet_fixtures.py --probe` parses every bundled real QET
  example without error (parser tolerance).
