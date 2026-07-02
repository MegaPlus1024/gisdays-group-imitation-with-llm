# Behavioral Trajectories Fixture Pack v1

This fixture pack (behaviour/behavioral wording equivalent) provides deterministic offline trajectories for validating normal user activity simulation scoring.

## Purpose
- provide stable behavioral validation trajectories;
- test role-appropriate vs role-inappropriate behavior;
- test repetitive/template-like patterns, low diversity, and history-aware behavior.

## Layout
- `trajectories/`: trajectory fixtures (single-role and multi-agent).
- `expected_results/`: robust score/verdict/flag expectations.

## Safety and execution
- fixtures are deterministic and offline-safe;
- fixtures do not execute actions;
- fixtures do not call LocalLLMClient or runtime endpoints.

## Intended use
Future model evaluation should reuse this fixture pack to compare model-generated trajectories against consistent behavioral expectations.
