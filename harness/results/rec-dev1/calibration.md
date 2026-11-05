# Calibration: rec-dev

Each stated claim's verdict against the strict scorer's match of that edge in the graph the reconciler read; each added claim's against its match in the graph it wrote. A verdict's `share false` is how often it was given to an edge gold does not support.

## a_sdk_agent+rec (6 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 139 | 183 | 0.568 |
| ambiguous | 2 | 3 | 0.600 |
| insufficient | 8 | 43 | 0.843 |
| contradicted | 4 | 8 | 0.667 |
| malformed | 11 | 20 | 0.645 |

Removed: 15 true edges, 28 false edges.

Added claims gold supports: 24 of 82.

## b_control+rec (19 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 287 | 563 | 0.662 |
| ambiguous | 10 | 83 | 0.892 |
| insufficient | 25 | 114 | 0.820 |
| contradicted | 0 | 55 | 1.000 |
| malformed | 24 | 27 | 0.529 |

Removed: 24 true edges, 82 false edges.

Added claims gold supports: 15 of 278.

## c_edc+rec (5 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 60 | 38 | 0.388 |
| ambiguous | 0 | 0 | - |
| insufficient | 0 | 29 | 1.000 |
| contradicted | 2 | 2 | 0.500 |
| malformed | 0 | 8 | 1.000 |

Removed: 2 true edges, 10 false edges.

Added claims gold supports: 43 of 126.

## corrupt+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 951 | 55 | 0.055 |
| ambiguous | 23 | 4 | 0.148 |
| insufficient | 60 | 424 | 0.876 |
| contradicted | 16 | 142 | 0.899 |
| malformed | 4 | 81 | 0.953 |

Removed: 20 true edges, 223 false edges.

Added claims gold supports: 226 of 463.

## dropped+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 1200 | 0 | 0.000 |
| ambiguous | 30 | 0 | 0.000 |
| insufficient | 59 | 13 | 0.181 |
| contradicted | 14 | 0 | 0.000 |
| malformed | 2 | 0 | 0.000 |

Removed: 16 true edges, 0 false edges.

Added claims gold supports: 134 of 248.

## gold+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 1406 | 0 | 0.000 |
| ambiguous | 48 | 0 | 0.000 |
| insufficient | 85 | 0 | 0.000 |
| contradicted | 18 | 0 | 0.000 |
| malformed | 2 | 0 | 0.000 |

Removed: 20 true edges, 0 false edges.

Added claims gold supports: 0 of 92.

