# Role Template And Constraint Format v1

## Purpose
Define a reusable format for persistent agent identity and behavioral constraints.

## Why role templates exist
Role templates prevent ad-hoc role definitions and make AgentState initialization consistent across scenarios.

## Relationship to AgentState
RoleTemplate describes persistent identity and behavioral constraints.  
AgentState describes current runtime state.

## Relationship to PromptContract
Prompt construction can include role and constraints from AgentState that was initialized from a RoleTemplate.

## Relationship to future Script Registry
RoleTemplate is not the Script Registry. Future semantic validation must still check actions against Script Registry.

## RoleTemplate fields
- `role_id`, `name`, `description`
- `primary_goals`, `success_criteria`
- `resources`
- `constraints`
- `allowed_activity_scenarios`
- `environment_assumptions`, `prompt_notes`, `metadata`

## ConstraintProfile fields
- network/model download constraints
- action execution prohibition flag
- allowed/forbidden file roots
- allowed/forbidden action names
- forbidden behaviors and safety notes

## Activity scenarios
Scenarios provide named, reusable context for what the role is expected to do and avoid.

## Examples
- `configs/role_template.example.json`
- `configs/roles/student_researcher.example.json`
- `configs/roles/developer.example.json`
- `configs/roles/office_worker.example.json`

## What this does not implement
- RoleTemplate does not execute actions.
- RoleTemplate does not validate action parameters.
- RoleTemplate is not the Script Registry.

## Done criteria
- role templates validate with Pydantic
- duplicate/contradictory constraint entries are rejected
- role templates can convert to AgentRole and AgentConstraints

## Next step
Future orchestrator may use RoleTemplate to construct AgentState.  
Future semantic validation layer should validate action names/parameters against Script Registry.
