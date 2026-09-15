# Analysis cases

Product records taken verbatim from real validation crawls, one JSON object
per line, as written by the `amazon_product` spider. Each file is the evidence
one category's rules were built against, and `../test_analysis.py` and
`../test_mounting_paste.py` assert the verdict on every record in it.

They are here because `data/` is gitignored, so the evidence every validation
rule was written against would otherwise live on one machine.

```
pasta_v1.jsonl.gz           25 records · dry pasta
mounting_paste_v1.jsonl.gz  29 records · tyre mounting paste
```

## `pasta_v1.jsonl.gz`

| Group | ASINs | Why |
|---|---|---|
| Disputed pack quantity | `B08JLSVW3J` `B08HQSZR3D` `B0173KFFIG` `B0BG28G6SZ` `B0C3WCFKHT` `B0C5XK2QFR` `B0BTPZ7TXJ` `B0GQ5BKHPT` | Amazon's attribute table contradicts the title or the pack-size name. Left unchecked these report €62.56/kg for a €3.91/kg pasta, and €0.32/kg for a €6.47/kg one. |
| Corroborated quantity | `B0CH3MHVF8` `B08BNQ2D54` `B0D4R7K82Q` `B0C2VN9NCD` `B00XUMS46W` | False-positive guards. Every one of these was disputed by an earlier version of the reconciler and is in fact correct. |
| Amazon's own figure is wrong | `B0G6D354JV` | Pack size confirmed by the title (20×500 g); Amazon's published price per kilo is the value that does not fit. |
| Implausible nutrition | `B089HJPK5T` `B0FWXQ6NWM` `B0FWXCDCYV` `B07NZ1K8L3` `B086K1MFSL` `B0BP2QDLPQ` | 534 g of protein per 100 g, a mistyped kJ column, a table header parsed as its own value, 7 g of carbohydrate in dry pasta. Five of the six come from Amazon's *structured* nutrition card. |
| Clean pasta | `B08WJGD5Z5` `B0DQ2N5HRW` `B0CT3Q17FP` | The comparison path, and proof the rules do not fire on ordinary records. |
| Not pasta | `B0CZ473RQT` `3969301173` | A cleaning brush and a cookbook, both returned by pasta searches. Classification is not optional. |

## `mounting_paste_v1.jsonl.gz`

The second category, added in R2. Its job is partly to guard the category's
own rules and partly to keep the *contract* honest: this is the set that made
three latent defects in the generic layer visible.

| Group | ASINs | Why |
|---|---|---|
| Mounting paste | `B01M25SBQ5` `B000RW5FVA` `B00295ER76` `B0GNMRKPGQ` `B0GNMSWB7D` `B0DHS9JHLJ` `B01LB62GQ2` `B01LB4QIEU` `B071JNV24H` `B001NYY87I` `B0FSRM9TBK` `B0055Y6M7Q` `B076HTCT4J` | Tubs, tubes, a sponge tin, an aerosol and three kits. `B0GNMRKPGQ` is one of only three listings in 43 that state the drying criterion the whole category turns on. |
| Near-miss product classes | `B097C8JJY4` `B0D1RJ1HLC` `B00CSRY8OC` `B0FJG6YJ2X` `B08VNDJJS6` | All five have "Montagepaste" in the title and none is one. Carbon paste is a *friction* paste — the opposite function; anti-seize and ceramic paste are designed never to dry; the last is a lubricant for repair plugs, caught by the `für` rule. |
| Accessories | `B01MXXA922` `B01M6WXE0X` | A brush named before the paste it is for. The positional rule that excludes them must not also exclude "5 kg paste **with** a brush". |
| Other products entirely | `B07V48PZY5` `B0CRTZ5ZJN` `B0C1GHMX8V` | Tubeless sealant, wheel weights, a pressure gauge — all returned by the same searches. |
| "Fett" is grease *and* fat | `B0068ICY70` `B07J2W1S6Q` `B0DGPV9TWZ` `B0F4PQ7NMM` | The food parser reads a pack size as a nutrition declaration: `"Fett wird in einer 100 g Tube geliefert"` → 100 g of fat per 100 g. Two of the four satisfy the per-100 g basis test, so only the single-nutrient corroboration rule stops them. |
| Volume pricing | `B0D6N5HYKB` `B007MFMN9W` | Priced per litre by Amazon. The first also states `2 x 75ml` against a 75 ml attribute total, which is a disputed pack quantity. |

## Privacy

These are product records, not page captures: they contain published product
data and the product URL, and no session identifiers, customer data or account
state. Unlike `../corpus/`, no redaction step is needed — the spider never
wrote anything per-session into a record.

## Updating

Add a record when a new rule needs evidence, or when a rule fires where it
should not. Take it verbatim from a crawl; do not hand-edit, or the case stops
being evidence of what Amazon actually publishes. A record may legitimately be
*re-extracted* from a retained page when the schema moves — that is not an
edit, it is the same bytes read by newer code, and it is what the page store
exists for.
