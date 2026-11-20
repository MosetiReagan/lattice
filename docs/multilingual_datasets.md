# Additional multilingual evaluation data

Prepared **17,825 additional records**: 3,794 TyDiQA Gold Passage questions in nine languages and 14,031 XQuAD questions in twelve configurations. Combined with the preserved curated intake, there are **211,455 unique normalized prompts**. The historical catalog is unchanged; the additive [inventory/audit](../benchmarks/datasets/manifests/multilingual-additions-v1.json) records both intakes and source hashes.

Counts are exported records, not independent tasks or model results. XQuAD contains translations of 1,189 question groups and derives from SQuAD v1.1. It is not twelve independent dataset families. Both additions are evaluation-only: do not train/tune on related SQuAD examples and claim independent XQuAD evaluation.

| Addition | Prepared | Source rows | Offset-check quarantines | Languages |
|---|---:|---:|---:|---|
| TyDiQA secondary task | 3,794 | 5,077 | 1,283 | Arabic, Bengali, English, Finnish, Indonesian, Korean, Russian, Swahili, Telugu |
| XQuAD | 14,031 | 14,280 | 249 | Arabic, German, Greek, English, Spanish, Hindi, Romanian, Russian, Thai, Turkish, Vietnamese, Chinese |

Every answer offset is checked against its exact context substring. If any answer in a row fails, the whole row is quarantined without repairing labels. These are offset-check failures, not proof that answer text is wrong: text can occur elsewhere and offset conventions/normalization may differ. Rejected IDs remain in manifests and original Parquet remains local. Exclusion changes the benchmark distribution; these are not official benchmark equivalents.

The audit checks schemas, hashes, counts and normalized prompts. No exact duplicates were found within/between these additions or against the historical curated exports. Framing differences, translations and shared passages can conceal related content; zero exact matches does not establish semantic independence or absent pretraining contamination.

## Provenance and terms

TyDiQA uses google-research-datasets/tydiqa revision da78f23f9119363459acbaf46bf89426ff26c259, secondary-task validation only. Card YAML declares Apache-2.0; its body licensing section is unspecified. This is an upstream declaration, not independent legal verification; underlying Wikipedia content retains source obligations.

XQuAD uses google/xquad revision 51adfef1c1287aab1d2d91b5bead9bcfb9c68583. Card YAML declares CC-BY-SA-4.0; its body licensing section is unspecified. Attribution remains with original XQuAD/SQuAD/Wikipedia contributors. [TyDiQA lock](../benchmarks/datasets/tydiqa.lock.json) and [XQuAD lock](../benchmarks/datasets/xquad.lock.json) pin raw URLs, sizes and SHA-256; byte-exact cards remain under source_audit.

MGSM was investigated but excluded: card metadata declares CC-BY-SA-4.0 while its body describes only original GSM8K MIT licensing. Candidate metadata/card remain as audit notes; no MGSM data was downloaded.

Raw/prepared content stays local, gitignored and outside code packages. Recipes, cards, hashes and inventories are committed. No blanket relicensing is claimed.

## Scoring limitations

Prompts use English instructions around original-language contexts/questions. Existing span_v1 normalization uses English articles/ASCII punctuation and is not validated as an official multilingual scorer. No model runs, accuracy, quality preservation or multilingual runtime support are claimed. Next steps require frozen language/article-stratified cases, validated multilingual scoring and measured tokenizer/context compatibility. These evaluation additions are not policy-training data.

## Reproduction

```bash
uv run --no-sync python scripts/prepare_tydiqa.py
uv run --no-sync python scripts/prepare_xquad.py
uv run --no-sync python scripts/audit_multilingual_additions.py
uv run --no-sync pytest -q tests/test_multilingual_data.py
```

Recipes verify pinned cards/raw hashes, quarantine offset failures and refuse changed exports/manifests. Both preparations reproduced byte-identical exports on a second run. Cross-intake auditing requires the previous curated exports; see [preparation instructions](datasets.md). No remote dataset code executes.
