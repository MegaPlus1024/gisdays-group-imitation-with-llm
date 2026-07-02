# Project objective: normal user activity simulation

## Original curator objective

The curator specification defines the project as development and experimental validation of an approach for simulating normal user activity by a group of local LLM agents.

## Correct project framing

The project is not only a safe local LLM action-selection pipeline.
The project objective is experimental validation of whether a group of local LLM agents can imitate plausible normal user activity in constrained computer environments.

## What "normal user activity" means in this project

In this project, normal user activity means role-plausible sequences of actions that look like realistic user work:
- aligned with a user role and goals
- constrained by available resources and environment rules
- selected from allowed parameterized scripts
- coherent across history, not random isolated steps

## Why safety validation is necessary but not sufficient

Safety and contract layers are required so experiments are reproducible and controlled.
However, safe execution alone does not prove behavioral normality.
A system can be safe but still produce unrealistic, repetitive, or role-incoherent trajectories.

## Relationship to local LLM agents

Local LLM agents are the decision engine for next actions.
They must choose actions autonomously using local inference, while staying within constraints and available scripts.

## Relationship to roles and constraints

Roles and constraints define what is plausible and allowed for each agent.
Behavioral evaluation must test whether generated trajectories remain role-compliant over time.

## Relationship to parameterized scripts

Scripts are parameterizable allowed actions, not a single fixed scenario.
Agents should choose among them based on state/history context instead of replaying one template path.

## Relationship to history-aware behavior

History-aware behavior is required for continuity.
Each step should account for previous actions, errors, and state changes so trajectory coherence can be evaluated.

## Relationship to multi-agent orchestration

The multi-agent layer supports group-level simulation experiments.
Current orchestration is smoke-level infrastructure and is not yet a production scheduler.

## Behavioral criteria for future evaluation

Future behavioral evaluation should include at least:
- role compliance
- coherence with prior history
- diversity of action patterns
- repeated/template behavior detection
- resource and latency footprint
- group-level differentiation (agents should not behave like identical clones)

## What is already implemented

Completed stages remain completed:
- Local Model Runtime
- Architecture and Design
- Parameterized Scripts
- Agent Prototype

Implemented technical foundation includes:
- local runtime and model smoke/baseline workflows
- strict NextAction and prompt contracts
- ScriptRegistry and ScriptExecutionBridge safety/control layers
- recovery policy and recovery-loop harness
- role-constrained trajectory and multi-agent smoke orchestration scaffolding
- history/error logging scaffolding

## What remains for Behavioral Evaluation Readiness

Behavioral Evaluation Readiness should add:
- explicit normal-activity profiles
- role/scenario fixture sets
- trajectory scoring rubrics
- evaluators for coherence, diversity, repetition/template behavior, and role fit
- reproducible behavioral report formats

## What remains for Experiments and Evaluation

Experiments and Evaluation should:
- compare local models on behavioral and resource metrics
- report failure modes and stability
- evaluate multi-agent scalability and differentiation
- produce evidence-backed conclusions about normal activity simulation quality

## Technical validity vs behavioral normality

A. Technical validity:
- valid JSON
- valid NextAction
- registry-accepted action
- safe path/command
- role-allowed action

B. Behavioral normality:
- action sequence looks plausible for the role
- actions are coherent with previous steps
- activity is diverse enough for the scenario
- behavior is not overly repetitive/template-like
- group agents resemble different users, not identical clones

## Done criteria

This objective reframe is complete when:
- documentation states the final goal is not only safe execution
- documentation states the final goal is evaluating whether local LLM agents can imitate normal user activity
- current architecture is presented as technical foundation for that evaluation
- next work is clearly framed as Behavioral Evaluation Readiness followed by Experiments and Evaluation
