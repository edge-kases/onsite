<!-- This is what Zixin shared with me in the email, but I converted it from pdf to markdown format for better usage to cc -->
# Interview Project: Enterprise Deployment Control Plane

## Time: 5 hours AI coding agents highly encouraged)
(You may simulate infrastructure instead of provisioning real cloud resources.)


## Background

Phylo deploys its platform to enterprise customers across different environments — AWS, GCP, Azure, and on-prem Kubernetes clusters. Today, deployment workflows are semi-manual and brittle. We want to move toward a clean, automated, scalable model.

Your job today is to design and build the first version of that system. You should approach this as the engineer responsible for defining how enterprise deployment works at Phylo. Make architectural decisions. Define contracts.Decide what belongs in the control plane vs the customer environment. Build what you think is the right first version.

We do not have a predefined “correct” architecture in mind. Weʼre interested in how you think, what tradeoffs you make, and how you structure the system.

Phylo deploys a containerized platform to enterprise customers. Each enterprise customer may run in a variety of environments, including AWS,
GCP, Azure, on-prem Kubernetes clusters and air-gapped or restricted enterprise environments.

As we grow, managing deployments across many enterprise environments becomes increasingly complex. Today, much of this process is manual or ad-hoc. We want to design a system that helps Phylo manage these deployments reliably and at scale. For example, such a system might help us:

- Track which version of the platform is running in each customer environment
- Safely roll out new versions
- Recover from or roll back failed deployments
- Operate in environments that cannot accept inbound connections
- Reduce the operational burden of maintaining many enterprise deployments

These examples are not meant to be exhaustive. Part of this exercise is deciding what the system should do and how it should work.

## The Tasks

Design and build a prototype system that could help Phylo manage deployments across many enterprise customer environments. This system does not exist yet. Your job is to propose an architecture and build a working prototype of the core ideas.

Some questions you may want to consider include:

- How should deployment state be tracked?
- How are deployments initiated and executed?
- How should the system interact with customer environments?
- How are failures detected and handled?
- How can the system scale to many tenants?
- What parts of the system run centrally vs inside customer environments?

In addition to core deployment workflows, you may also build features that help reduce the operational burden of managing many enterprise deployments. This could include automation, operational tooling, observability, or AI-assisted systems that help diagnose or resolve issues. These are optional — feel free to explore ideas that make operating the system easier at scale

The goal is not to build a production-ready distributed system, but to demonstrate a clear architectural approach and a working prototype of the core concepts. Choose what is appropriate for a 5-hour sprint.

## Deliverables

Please push everything to a GitHub repository and share the link before the end-of-day session.

### Working Prototype
An end-to-end demo-able system that we should be able to run it locally and see the system operate.

### Design Notes
Provide a short design write-up describing your system. This can be a short
document or notes in the repository. Include:

- Architecture diagram (using a tool like Excalidraw or similar)
- Key components of the system and their responsibilities
- Key design decisions and tradeoffs

You do not need to write a long document — focus on clearly explaining your approach.

Optionally, you may include:
- Ideas for how the system could evolve in production
- What you intentionally left out given the time constraint
- Security model

### AI Session Transcripts
Include AI coding agent session transcripts in the repository. We want to understand how you decomposed the problem and steered AI tools.

## End-of-Day Session
Weʼll walk through:
- Your architecture
- Your design decisions
- Live demo of your system
- Failure handling logic
- How you used AI during development
- What youʼd build next