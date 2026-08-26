"""The pipeline stages.

One module per stage of the CERNAL Computational Pipeline Map, named so that someone
reading the map can find the code. Each stage is a class holding read-only
configuration and the tools it uses, with one public method taking the previous stage's
records and returning the next (docs/engine.md §3.1).

Stages hold configuration, never accumulated state — that distinction is what keeps
each one testable in isolation (docs/engine.md §2.3).
"""
