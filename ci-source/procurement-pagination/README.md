# Original Procurement qualification transport

The existing source-controls PR job verifies this carrier without native workloads.
The original native `validate` job remains disabled (`if: false`). Publication and
ordinary repo PR CI do not provide qualification acceptance or an allocation.

The coordinator must reserve a fresh nonce for exactly one dispatch in its
existing allocation ledger and supply exact allocation JSON bytes and SHA256
after reviewing the published transport commit. Admission checks the first hosted
attempt, exact source/run tuple, UTC expiry (at most3600s), unchanged60-minute job
cap and fresh4GiB floor before SDK setup. Actual class ownership/PG18 health,
terminal absence, exact16RED/94GREEN/full410 and separate9 injections remain unrun.

Source controls: `python -B -Werror ci-source/procurement-pagination/tests/compile_source.py`,
`python -B ci-source/procurement-pagination/p1-controls.py`, and
`python -B -m unittest discover -s ci-source/procurement-pagination/tests -v`;
repeat controls with `-O` to ensure guards remain active under optimization.

Runtime assets retain exact independently reviewed V4 bytes; only caller's
existing PR source-controls trigger/job and regression-test paths are adapted.
V4 manifest d2a655213a67b85469c60888edaaee2a7d1804087408ffca978987ad63e3330c
V4 seal43b209e18d38f565a2e955600a9ee6ac5dfdfc9f943e34e7968805494eca9c7a
V3 manifest30c41380a1079d979376aaf9eff61594092eae0d13421fb44823ff5432eb211e
V3 seal2c0938b9406553755f820bb1f85f5bf55de73d9e7d64b824a6264c1978abb2ce
