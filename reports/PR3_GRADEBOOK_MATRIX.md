# PR3 Gradebook matrix

## States
| Status | Points | Category avg | Notes |
|---|---|---|---|
| graded | required finite | included | override audited |
| ungraded | null | excluded until scored | display only |
| missing | 0 if missing_as_zero | included as 0 | policy-driven |
| late | points × (1 − penalty%) | included | late_penalty_pct |
| excused | null | excluded | medical etc. |

## Aggregation
- Item percent = points_earned / points_possible × 100 (fail-closed on NaN/Inf)
- Category percent = mean of non-excused item ratios (optional drop_lowest)
- Overall = weighted mean of category percents by category.weight
- No NaN/Inf allowed in outputs (ServiceError GRADEBOOK_NAN / INVALID_POINTS)

## Evidence
- `tests/pr3/test_gradebook.py`
- Instructor matrix + learner own-scores view via `GET /api/v1/sections/{id}/gradebook`
- Override audits via `GET /api/v1/gradebook/entries/{id}/overrides`
