# Research index

These are dated source studies, not running status documents. For current capability
read the [handoff](../archive/2026-10-28-handoff.md); for measured local outcomes read the
[experiment record](../experiments/recognition.md).

## Recognition

Read in this order:

1. [ISL recognition landscape](recognition/landscape.md): methods, datasets and
   practical model choices.
2. [Source audit](recognition/source-audit.md): exact artifacts, preprocessing,
   metric provenance, splits and licensing.
3. [ASL-to-ISL transfer](recognition/asl-transfer.md): the evidence behind frozen
   features plus labeled ISL references before training a new classifier.
4. [Independent Ishaara AI audit](recognition/ishaara-ai-audit.md): what their GRU,
   image detector and website actually demonstrate, and limits on reuse.

[Earlier reuse options](recognition/reuse-options.md) records the initial
checkpoint search. Its proposed ordering predates the local experiments.

## Speech and device

- [Bolna integration paths](speech-device/bolna-paths.md): the later OSS
  text/audio route and engineering gaps.
- [Demo feasibility](speech-device/demo-feasibility.md): device/backend
  composition and implications for the demonstration.
- [iOS and workflow evidence](speech-device/ios-and-workflow.md): platform
  boundaries and consulted sources.
- [Earlier Bolna/call audit](speech-device/bolna-and-calls.md): original hosted
  interface checks. Read alongside the later integration-path study.

## Product and sources

- [Product directions](product-directions.md): why the seated appointment is the
  current focus and which alternatives would change the product.
- [Everyday workflows](everyday-workflows.md): supporting use-case research.
- [Source claim ledger](../CLAIM-LEDGER.md): evidence qualifications and URL inventory.
- [Original research leads](links.md): supplied links, not blanket endorsements.
- [Archive](../archive/README.md): superseded synthesis, plans and task briefs.

Keep study dates and source qualifications when updating these files. A paper's
benchmark, a public model listing and a local runtime observation are different
forms of evidence. Code, model and dataset licenses also need separate treatment.
