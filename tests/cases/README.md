# Analysis cases

25 product records taken verbatim from the 195-record Amazon.de validation
crawl, one JSON object per line, as written by the `amazon_product` spider.
`../test_analysis.py` runs the pasta analysis over them and asserts the verdict
on each.

They are here because `data/` is gitignored, so the evidence every validation
rule was written against would otherwise live on one machine. Each record is
the reason a rule exists:

| Group | ASINs | Why |
|---|---|---|
| Disputed pack quantity | `B08JLSVW3J` `B08HQSZR3D` `B0173KFFIG` `B0BG28G6SZ` `B0C3WCFKHT` `B0C5XK2QFR` `B0BTPZ7TXJ` `B0GQ5BKHPT` | Amazon's attribute table contradicts the title or the pack-size name. Left unchecked these report €62.56/kg for a €3.91/kg pasta, and €0.32/kg for a €6.47/kg one. |
| Corroborated quantity | `B0CH3MHVF8` `B08BNQ2D54` `B0D4R7K82Q` `B0C2VN9NCD` `B00XUMS46W` | False-positive guards. Every one of these was disputed by an earlier version of the reconciler and is in fact correct. |
| Amazon's own figure is wrong | `B0G6D354JV` | Pack size confirmed by the title (20×500 g); Amazon's published price per kilo is the value that does not fit. |
| Implausible nutrition | `B089HJPK5T` `B0FWXQ6NWM` `B0FWXCDCYV` `B07NZ1K8L3` `B086K1MFSL` `B0BP2QDLPQ` | 534 g of protein per 100 g, a mistyped kJ column, a table header parsed as its own value, 7 g of carbohydrate in dry pasta. Five of the six come from Amazon's *structured* nutrition card. |
| Clean pasta | `B08WJGD5Z5` `B0DQ2N5HRW` `B0CT3Q17FP` | The comparison path, and proof the rules do not fire on ordinary records. |
| Not pasta | `B0CZ473RQT` `3969301173` | A cleaning brush and a cookbook, both returned by pasta searches. Classification is not optional. |

## Privacy

These are product records, not page captures: they contain published product
data and the product URL, and no session identifiers, customer data or account
state. Unlike `../corpus/`, no redaction step is needed — the spider never
wrote anything per-session into a record.

## Updating

Add a record when a new rule needs evidence, or when a rule fires where it
should not. Take it verbatim from a crawl; do not hand-edit, or the case stops
being evidence of what Amazon actually publishes.
