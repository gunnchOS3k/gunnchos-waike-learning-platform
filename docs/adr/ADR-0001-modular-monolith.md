# ADR-0001: Modular monolith

## Status

Accepted (PR 1)

## Context

PR 1 needs a client, compiler, contracts, and a hub scaffold without operational complexity.

## Decision

Ship a modular monolith monorepo. Separate domains by directory (`apps/`, `services/`, `tools/`, `contracts/`) without microservices, Kafka, or Kubernetes.

## Consequences

Faster iteration and shared contracts. Future extraction remains possible once product boundaries stabilize.
