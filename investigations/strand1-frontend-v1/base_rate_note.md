# Why README said 17.8% but the split table said 20.8%

Both numbers are correct; they use **different denominators**.

## README / metrics B: **17.8%**

- Stratum: eval rows with **`jp_ctx == jp_default` only** (n = 37011)
- Numerator: realized ≠ default among those rows (n = 6598)
- Rate: 6598 / 37011 = **0.178271 ≈ 17.8%**
- This is also `metrics.json → B_change_decision.base_rate_realized_ne_default`.

## Comparison table `eval_should_change`: **20.8%**

- Stratum: **all** eval judgeable rows (n = 38758), **including** `jp_ctx ≠ jp_default`
- Numerator: `eval_should_change` = realized ≠ default on all eval (n = 8051)
- Rate: 8051 / 38758 = **0.207725 ≈ 20.8%**

## Why they differ

When `jp_ctx ≠ jp_default`, ToJyutping already left the default reading. Those rows still count toward “realized≠default” in the all-eval table, but they are **excluded** from the change-decision base rate (which only asks “should we override default?” when ctx is still default).

Check: all-eval should_change 8051 − ctx=default realized≠default 6598 = **1453** rows with realized≠default and ctx≠default (plus a few with realized=default & ctx≠default in the 1747 ctx≠default block).

| definition | den | num | rate |
|---|---|---|---|
| ctx=default only (README / B) | 37011 | 6598 | 17.8% |
| all eval (table should_change) | 38758 | 8051 | 20.8% |

No corpus or split bug — just mismatched strata in the prose vs the split summary table.
