# Calibration: rec-dev

Each stated claim's verdict against the strict scorer's match of that edge in the graph the reconciler read; each added claim's against its match in the graph it wrote. A verdict's `share false` is how often it was given to an edge gold does not support.

## a_sdk_agent+rec (6 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 140 | 183 | 0.567 |
| ambiguous | 2 | 3 | 0.600 |
| insufficient | 8 | 43 | 0.843 |
| contradicted | 4 | 8 | 0.667 |
| malformed | 10 | 20 | 0.667 |

Removed: 14 true edges, 28 false edges.

Added claims gold supports: 24 of 30.

## b_control+rec (19 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 311 | 563 | 0.644 |
| ambiguous | 10 | 83 | 0.892 |
| insufficient | 25 | 115 | 0.821 |
| contradicted | 0 | 54 | 1.000 |
| malformed | 0 | 27 | 1.000 |

Removed: 0 true edges, 81 false edges.

Added claims gold supports: 31 of 235.

## c_edc+rec (5 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 60 | 38 | 0.388 |
| ambiguous | 0 | 0 | - |
| insufficient | 0 | 30 | 1.000 |
| contradicted | 2 | 1 | 0.333 |
| malformed | 0 | 8 | 1.000 |

Removed: 2 true edges, 9 false edges.

Added claims gold supports: 42 of 75.

## corrupt+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 952 | 55 | 0.055 |
| ambiguous | 23 | 4 | 0.148 |
| insufficient | 64 | 488 | 0.884 |
| contradicted | 13 | 78 | 0.857 |
| malformed | 2 | 81 | 0.976 |

Removed: 15 true edges, 159 false edges.

Added claims gold supports: 161 of 242.

## dropped+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 1201 | 0 | 0.000 |
| ambiguous | 30 | 0 | 0.000 |
| insufficient | 61 | 13 | 0.176 |
| contradicted | 13 | 0 | 0.000 |
| malformed | 0 | 0 | - |

Removed: 13 true edges, 0 false edges.

Added claims gold supports: 134 of 163.

## gold+rec (20 cases)

### stated claims

| verdict | true edges | false edges | share false |
|---|---|---|---|
| supported | 1407 | 0 | 0.000 |
| ambiguous | 48 | 0 | 0.000 |
| insufficient | 90 | 0 | 0.000 |
| contradicted | 14 | 0 | 0.000 |
| malformed | 0 | 0 | - |

Removed: 14 true edges, 0 false edges.

Added claims gold supports: 0 of 28.

