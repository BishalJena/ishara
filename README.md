# Ishara

Ishara explores a mobile interface that turns a bounded set of Indian Sign Language inputs into speech during an ordinary phone conversation, helping an adult ISL signer communicate with a hearing person.

**Current phase: Bolna backend feasibility prototype.** The immediate work is to prove user-approved text → Bolna audio → controllable playback/cancellation, followed by a minimal iPhone call-audio diagnostic if the backend passes. Product app UX and recognition integration come after that checkpoint. A teammate can independently validate a pretrained recognizer now. The user's ordinary own-number call remains the target; camera/AAC/captions, language support and recognition performance are not yet validated.

Start with the [research findings and evidence map](docs/RESEARCH.md). Requirements, architecture and delivery tickets follow validation and scope decisions.

For the recognition teammate: [validate the pretrained AI4Bharat INCLUDE model](docs/tasks/validate-include-recognizer.md). The brief includes exact checkpoint sizes, pinned source, validation steps and a results checklist.
