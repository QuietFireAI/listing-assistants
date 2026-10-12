# Agent 05 - Predeliberated Decisions (Tuple Layer) v0.1 (ratified 2026-07-11)

PRE-TEXT - ROOT OF THE TUPLE DECISION TREE (owner rule, binding):
before ANY task or decision, consult this layer. If NO suitable tuple covers
the task: STOP. Contact the human via clarification.request and wait. Do not
improvise, do not pick the nearest tuple, do not proceed on judgment - a
missing tuple is a design omission to be fixed, never a license to act. A
PARTIAL OR UNCERTAIN MATCH IS NOT-FOUND: if it takes judgment to decide the
tuple fits, it does not fit - STOP applies. The after-action proposes the
missing tuple so the omission is closed.

Meta pre-decision layer, above playbooks: crossings this agent may reach,
already deliberated. Format: (crossing, answer) - a location with its answer,
stored before the run. Swarm-wide tuples in /SWARM.md apply first; MANNERS.md
constrains everything.

- (supplied data has no valid MLS field, clarification; never approximate into the wrong field)
- (syndicated portal shows different data than MLS, correct the source record, then re-verify every portal)
- (two authorized changes conflict, execute neither; human)
- (portal still stale after the verification window, log + notify human; never mark complete)
- (status change requested without its required artifact, refuse; artifact first)
- (status change requested without signed listing.change.authorized, refuse; verbal or email instruction is not authority)
- (MLS rejects an entry on a rule, log raw rejection, human; never adjust data to pass validation)
- (price in the authorized change conflicts with the agreement amendment on file, halt; both documents to human)
- (comp-offer field present anywhere, leave blank per 8/17/24 rules; flag any request to fill it)
- (listing data and marketing asset disagree, MLS record is truth; asset.release corrected version; discrepancy logged)
- (withdrawal requested while under contract, halt; 17 + human; status math on a live contract is never autonomous)

Added 2026-10-12 (owner sign-off, Jeff: modules wired, J3/J4/J8 decisions):
- (listing marked vacant by the broker, order a property condition check through 09 every interval until occupied or the listing ends; a check counts only with proof)
- (vacant listing ends or is marked occupied, stop the watch and log it to 14)

Code status (checked 2026-10-12): three tuples need an MLS or portal
connection this build does not have and cannot fire - syndicated portal
differs from MLS, portal still stale, MLS rejects an entry. "asset.release
corrected version" is done as a corrected `listing.data` to Agent 04, which
rebuilds the asset (this agent has no route to send `asset.release`).

(Root rule, restated: no suitable tuple - or an uncertain match - means STOP and ask the human.)
