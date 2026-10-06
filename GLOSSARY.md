# Planogram

Compares photos of retail shelves against planned shelf layouts, and builds layouts from photos, for management reporting.

## Language

### Organisation

**Store**:
One retail location belonging to the organisation, holding its own Fixtures.
_Avoid_: Shop, outlet, site, location

**Viewer**:
A person who can see Compliance Checks, Annotated Photos and their history.

**Operator**:
A person who can also submit Shelf Photos for Extraction and Compliance Checks.
_Avoid_: Uploader, staff

**Manager**:
A person who can also correct Draft Planograms, approve them, and add Products to the Product Catalogue.
_Avoid_: Admin, approver, supervisor

### Layout

**Fixture**:
A named run of shelving in a Store, made up of numbered Bays, such as "Drinks" with Bays 1/4 to 4/4.
_Avoid_: Gondola, run, aisle

**Bay**:
One numbered vertical section of a Fixture, such as "Drinks 2/4".
_Avoid_: Module, unit, column, section

**Shelf**:
One horizontal level within a Bay, counted from the bottom.
_Avoid_: Row, level, tier

**Facing**:
One unit of a product visible from the front of a Shelf.
_Avoid_: Slot, spot

**Block**:
A run of adjacent Facings of the same Product on one Shelf.
_Avoid_: Group, cluster, segment

**Position**:
Where a Block sits in a Planogram: its Bay, its Shelf, its order from the left on that Shelf, and its number of Facings.
_Avoid_: Location, placement, coordinates

### Planograms

**Planogram**:
The planned layout of Products on a Fixture: which Product sits at which Position.
_Avoid_: Layout, shelf plan, POG

**Draft Planogram**:
A Planogram under review after Extraction, which a manager may still correct.
_Avoid_: Proposed planogram, candidate

**Approved Planogram**:
A Planogram a manager has signed off as the reference for Compliance Checks; it never changes afterwards.
_Avoid_: Master planogram, baseline, golden planogram

**Superseded Planogram**:
An Approved Planogram replaced by a newer one for the same Fixture, kept so past Compliance Checks still refer to what they were measured against.
_Avoid_: Old planogram, archived, deleted

### Products

**Product**:
An item the organisation stocks, identified by its SKU, with a name and one or more reference images.
_Avoid_: Item, article

**Product Catalogue**:
The complete set of Products the organisation may stock, shared by all its Stores and used as the reference for recognising products on a shelf.
_Avoid_: Master data, product list, assortment

**Unknown Product**:
Something on a shelf that cannot be matched to any Product in the Product Catalogue.
_Avoid_: Unrecognised item, other

### Operations

**Shelf Photo**:
A photo showing exactly one whole Bay, tagged with which Bay it shows.
_Avoid_: Image, capture, snapshot

**Extraction**:
Building a Draft Planogram from a Shelf Photo of a Bay as it currently stands.
_Avoid_: Generation, detection

**Compliance Check**:
A comparison of a Shelf Photo against the Approved Planogram current for its Bay at the time, producing Deviations and a Compliance Score.
_Avoid_: Audit, validation

**Deviation**:
One difference found by a Compliance Check, classified as exactly one of Gap, Missing, Wrong Facing Count, Misplaced, or Unexpected.
_Avoid_: Issue, error, violation

**Gap**:
A Deviation where planned Facings of a Product are absent and their Shelf space is empty, signalling a likely out-of-stock.
_Avoid_: Hole, void, OOS

**Missing**:
A Deviation where a planned Product is absent and its Shelf space is taken by something else.

**Wrong Facing Count**:
A Deviation where a Product is in its planned place with more or fewer Facings than planned, without leaving empty space.

**Misplaced**:
A Deviation where the right Product is on the wrong Shelf or in the wrong order within the same Bay.

**Unexpected**:
A Deviation where something on the Shelf is not in the Approved Planogram, including any Unknown Product.

**Unverified**:
An area of a Shelf Photo where recognition was not confident enough to report a Deviation or confirm compliance; it counts as neither.
_Avoid_: Uncertain, low-confidence, unknown

**Compliance Score**:
The percentage of a Bay's verified planned Facings that are present in their correct Position; Unverified Facings are left out.
_Avoid_: Compliance rate, KPI

**Coverage**:
The percentage of a Bay's planned Facings that a Compliance Check could verify, shown alongside the Compliance Score.
_Avoid_: Confidence, completeness

**Annotated Photo**:
A Shelf Photo with a Compliance Check's Deviations labelled on top of it.
_Avoid_: Overlay, marked-up image
