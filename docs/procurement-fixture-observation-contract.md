# Fixture observation contract

Outer receipt schema 2 uses `one-running-snapshot-full-id-census-v1`.

The independent observer acquires one running snapshot for every full container ID.
Acquisition records the actual limits, loopback bindings, role, run and parent labels,
provider birth/start times, PID, finite expiry, session and volumes. A resource first
seen before it is running must still acquire its running snapshot. A full ID with a
previously acquired running snapshot is tracked by successful full-ID censuses;
the observer does not inspect that resource again.

This proves a running-state snapshot, not continuous monitoring of limits, labels,
or provider state. Later configuration mutation is outside this contract. Full
Docker IDs must match inspection results exactly. Short IDs, duplicated census
IDs, invalid ownership, birth/lease, limits or binding data fail acquisition. A new
full ID sharing an acquired resource's short prefix still requires acquisition.

Any failed inspection of an unknown resource remains a failure, including a 404.
There is no tombstone acceptance and no reinterpretation of historical failed
receipts. Acquisition attempts continue for the other independently listed
resources and retain all original errors. Terminal resource observations likewise
attempt the other session, container and volume queries under the existing shared
deadline and preserve every failure. Failed censuses explicitly retain uncertainty.

Qualification still requires all five independent running snapshots, the frozen
18-case native roster, all three provider terminal receipts, natural process and
session absence, exact container and volume absence, no pending handles, and no
observation errors or command failures. Extra session resources, late volumes,
missing snapshots, timeout or daemon failures prevent qualification. The observer
never deletes containers or volumes. Existing signal ownership, byte/cardinality
limits, native deadline, shared cleanup deadline and command admission remain.

Provider-free regression controls cover known acquired removal, unknown removal,
short-prefix collisions, missing fifth resource, wrong birth/labels, pre-running
acquisition, late session resources and volumes, shared deadlines and multiple
original errors. Passing these controls does not qualify native cleanup. New
hosted execution and its original artifacts are required for schema 2 acceptance.

The final process census runs independently after the Docker census attempt,
including when Docker acquisition or a session/global query fails. It retains late
process identities and closes every acquired PID handle. This census shares the
original cleanup deadline, checked before process reads and during enumeration.
An exhausted deadline or census error records explicit process uncertainty and
all original errors; it never grants a new cleanup interval or qualifies absence.
