# Architecture decisions

This record outlines the core technical decisions governing SkillTwin.

## Decision 1: Project naming and identity

- Decision: Use the project name SkillTwin uniformly across code, schemas, and documentation.
- Context: Unifies product identity and prevents outdated naming inconsistencies.
- Status: Accepted

## Decision 2: Schema first boundary definition

- Decision: Shared JSON Schema draft 2020 12 files in packages/contracts govern all inter service communication.
- Context: Multiple languages (Python and TypeScript) participate in the pipeline. Single source schemas prevent drift.
- Status: Accepted

## Decision 3: Fixed six step template for initial release

- Decision: The fragilePackingV1 workflow strictly enforces six actions in fixed sequence: selectProduct, selectBox, addProtection, placeProduct, sealBox, attachLabel.
- Context: Eliminates hallucinations and ensures predictable packing procedure structure.
- Status: Accepted

## Decision 4: Mandatory supervisor approval

- Decision: Model composed drafts are reviewRequired with version 0. An approved skill requires explicit human supervisor sign off, producing an immutable positive version.
- Context: Autonomous model outputs must never reach packing floor workers without human verification.
- Status: Accepted

## Decision 5: Policy conflict transparency

- Decision: When demonstration video actions conflict with written policy requirements, the conflict is explicitly flagged and presented with citation excerpts in supervisor review.
- Context: Operators must know when recorded practices deviate from formal compliance standards.
- Status: Accepted

## Decision 6: Local execution and testability

- Decision: All skeleton services and mock adapters operate locally without requiring active AWS credentials or cloud dependencies.
- Context: Enables rapid automated testing and contributor onboarding.
- Status: Accepted
