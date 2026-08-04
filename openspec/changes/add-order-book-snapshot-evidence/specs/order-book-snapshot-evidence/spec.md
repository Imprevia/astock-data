## ADDED Requirements

### Requirement: Structured five-level order-book snapshot

The system SHALL expose a resolver-backed five-level order-book snapshot from Tencent real-time quotes with explicit price and lot-volume fields.

#### Scenario: Complete Tencent quote is returned

- **WHEN** Tencent returns a full quote payload for a valid A-share ticker
- **THEN** the result contains the vendor timestamp, last price, up to five bids, up to five asks, visible depth totals, spread, and source metadata

#### Scenario: A visible level is missing

- **WHEN** a Tencent price level is empty, zero, or malformed
- **THEN** the level is omitted and the system MUST NOT invent a replacement price or volume

### Requirement: Bounded snapshot sampling

The system SHALL support bounded multi-sample collection without introducing an unbounded daemon or background process.

#### Scenario: Caller requests multiple samples

- **WHEN** `samples` and `interval_seconds` satisfy the configured bounds
- **THEN** the service collects snapshots in order and records the requested sampling metadata

#### Scenario: Sampling request exceeds the bound

- **WHEN** the sample count, interval, or planned total wait exceeds its allowed range
- **THEN** the public entrypoint rejects the request before any network call

#### Scenario: A later sample fails

- **WHEN** at least one snapshot succeeds and a later request fails
- **THEN** the result preserves successful snapshots and records the failed sample in warnings

### Requirement: Truthful visible-depth changes

The system SHALL compare consecutive distinct-timestamp snapshots by side and price while preserving attribution uncertainty.

#### Scenario: Volume decreases at the same visible price

- **WHEN** the later snapshot has less volume at a price that remains visible on the same side
- **THEN** the result emits `depth-decrease` with `attribution=unattributed` and MUST NOT label it a cancellation

#### Scenario: A price leaves the visible five levels

- **WHEN** a previously visible price is absent from the next snapshot
- **THEN** the result emits `left-view` and MUST NOT claim the underlying order was removed

#### Scenario: Vendor timestamp is unchanged

- **WHEN** consecutive samples carry the same vendor timestamp
- **THEN** the system does not emit a change between them

### Requirement: One-to-one public adapters

The system SHALL expose the order-book capability through matching Python API, CLI, and MCP entrypoints.

#### Scenario: Default invocation

- **WHEN** a caller omits sampling options
- **THEN** each public adapter requests one snapshot without an intentional wait

#### Scenario: Adapter serialization

- **WHEN** an adapter returns a successful result
- **THEN** it preserves the same structured model fields, warnings, source, and exact-cancellation capability flag

### Requirement: Buyer-exhaustion date isolation

The buyer-exhaustion analysis SHALL consume order-book evidence only when it matches the current target date and SHALL degrade independently when it is unavailable.

#### Scenario: Current-date distinct snapshots are available

- **WHEN** at least two snapshots have distinct timestamps on the target date
- **THEN** the analysis may report visible depth changes while describing decreases as unattributed

#### Scenario: Only one or static snapshot is available

- **WHEN** the target date has fewer than two distinct snapshot timestamps
- **THEN** the analysis reports current visible depth but identifies intraday change and cancellation evidence as unavailable

#### Scenario: Target date is historical

- **WHEN** the requested target date is earlier than the current local date
- **THEN** the analysis MUST NOT request or attach a current order-book snapshot to that historical date

#### Scenario: Order-book retrieval fails

- **WHEN** the order-book command fails or returns no matching snapshot
- **THEN** the base buyer-exhaustion analysis remains available and records a dynamic data limitation
