# Source licensing audit snapshots

Active authoritative dataset-card URLs, immutable revisions and SHA-256 are in [sources.lock.json](../sources.lock.json). Snapshot files remain upstream content under their own terms. They are collected for attribution/provenance and do not become Apache-2.0 Lattice code.

Additional upstream READMEs/licenses and excluded-source cards are supporting intake notes. Only snapshots referenced by the source lock are required to reproduce downloads. Supplemental files fetched during investigation are not automatically authoritative pinned licensing evidence.

Winogrande's upstream README at commit `727e837f77521ef38bcc56df3b275c8da43f45af` distinguishes Apache-2.0 code from CC-BY data without an explicit version. It was excluded from active preparation. Do not infer dataset terms from a repository's code LICENSE alone. HellaSwag, OpenBookQA and SocialIQA exclusions are recorded in the lock.

See [datasets.md](../../../docs/datasets.md) for source links, terms and limitations. No third-party model weights or generated code executions are part of this audit.

The pinned WikiText card conflicts internally: YAML lists CC-BY-SA 3.0/GFDL, while its licensing section states CC-BY-SA 4.0. [license-errata-v1.json](../license-errata-v1.json) overrides the historical inferred OR label in the curated catalog. No legal license operator is inferred and no corpus redistribution rights are granted by Lattice. The original card remains byte-exact.
