# CERNAL Architecture Canvas Vault

This folder is designed to be opened directly as an **Obsidian vault**.

Start here:

- [[CERNAL Architecture.canvas]]

The root canvas links to every detailed map. Each detailed canvas contains a **Home** file-node linking back to the root, plus several related canvases.

## Architectural rule

CERNAL consists of two deliberately separate systems:

1. **CERNAL Platform** — the user-facing product.
2. **CERNAL Engine** — an independently deployed scientific computation service.

The Platform calls the Engine through a versioned asynchronous service API. Slurm, scientific tools, gate logic and scoring remain behind the Engine boundary.

## Canvas index

- [[Maps/01 System Boundary.canvas]]
- [[Maps/02 Researcher Workflow.canvas]]
- [[Maps/03 Frontend Architecture.canvas]]
- [[Maps/04 Backend Architecture.canvas]]
- [[Maps/05 Platform Domain and Database.canvas]]
- [[Maps/06 Platform Async Orchestration.canvas]]
- [[Maps/07 Platform Run State Machine.canvas]]
- [[Maps/08 Platform-Engine API Contract.canvas]]
- [[Maps/09 End-to-End Analysis Sequence.canvas]]
- [[Maps/10 Engine Architecture.canvas]]
- [[Maps/11 Scientific Pipeline.canvas]]
- [[Maps/12 Gate and Scoring Architecture.canvas]]
- [[Maps/13 Engine Job State Machine.canvas]]
- [[Maps/14 Compute Provider and Slurm.canvas]]
- [[Maps/15 Storage and Artifact Flow.canvas]]
- [[Maps/16 Security and Trust Boundaries.canvas]]
- [[Maps/17 Deployment Topologies.canvas]]
- [[Maps/18 Reliability Reproducibility Observability.canvas]]
- [[Maps/19 Repository and Team Ownership.canvas]]
- [[Maps/20 Implementation Roadmap.canvas]]

## Color convention

The canvases use Obsidian's standard color palette:

- **Cyan/blue**: CERNAL Platform / product software
- **Green**: CERNAL Engine / scientific service
- **Purple**: Compute/HPC infrastructure
- **Orange**: Storage / persistence
- **Red**: Security, failure or exception paths
- **Yellow**: Contracts, navigation or cross-cutting architecture

## Portability

Canvas file nodes use **vault-relative paths** such as `Maps/08 Platform-Engine API Contract.canvas`.
For links to work without editing paths, either:

- unzip this entire folder and open `CERNAL_Architecture_Vault` as an Obsidian vault, or
- copy the **contents** of this folder into the root of an existing vault.

