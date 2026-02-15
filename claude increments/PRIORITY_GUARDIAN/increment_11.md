Integration Test Briefing: Goal Mutation Endpoints + Minor Coverage Additions

Context
test_pg_mutation_endpoints.py covers priorities and deliverables (Inc B) but was never extended for goal endpoints (Inc D). Goal CRUD endpoints exist in priorities_router.py and are fully implemented. This briefing adds integration test coverage to close the gap.
Prerequisite Fix: conftest.py TRUNCATE
The cleanup_db fixture in tests/conftest.py does NOT include pg_goals in the TRUNCATE statement. This will cause test pollution.
Current:
"TRUNCATE TABLE focused_focus_sessions, focused_user_keywords, "
"focused_scheduled_jobs, clarity_clusters, "
"pg_weekly_snapshots, pg_deliverables, pg_priorities, "
Required: Add pg_goals before pg_deliverables (FK ordering):
"pg_weekly_snapshots, pg_goals, pg_deliverables, pg_priorities, "
This is the only code change outside the test file.

File to Create
tests/integration/priority_guardian/test_pg_goal_endpoints.py
Existing Patterns to Follow
Mirror the structure in test_pg_mutation_endpoints.py:

Same helper functions: create_test_user, create_test_priority, same fixtures (client, async_session)
Add new helper: create_test_goal(async_session, priority_id, text, achieved=False) using PgGoal model
Same assertion pattern: every mutation returns 200/201 with full priorities response containing goals array

Import Requirements
pythonfrom backend.apps.priority_guardian.db_models import PgPriority, PgGoal
Endpoints Under Test
EndpointMethodRouter PathCreate goalPOST/api/priority-guardian/priorities/{priority_id}/goalsUpdate goalPUT/api/priority-guardian/goals/{goal_id}Delete goalDELETE/api/priority-guardian/goals/{goal_id}
Test Classes and Cases
TestCreateGoalEndpoint
TestWhat it provesExpectedtest_create_goal_on_flexible_priorityHappy path: goal created, returned in priorities response201, goals array has 1 item, text matches, achieved=Falsetest_create_goal_on_deadline_priority_returns_422Type enforcement: goals only for flexible422, code=VALIDATION_ERROR, message mentions "flexible"test_max_goals_returns_409Limit enforcement: max 3 goals per priorityCreate 3 goals first, then attempt 4th → 409, code=MAX_GOALS_REACHEDtest_returns_404_for_nonexistent_priorityFK validation404test_returns_404_for_different_userOwnership enforcement404test_returns_422_for_missing_textPydantic validation on {} body422test_returns_422_for_long_textMax length: 201 chars422test_returns_422_for_whitespace_only_textWhitespace validation422
TestUpdateGoalEndpoint
TestWhat it provesExpectedtest_toggle_achieved_to_trueHappy path toggle200, goal.achieved=Truetest_toggle_achieved_to_falseReverse toggle200, goal.achieved=Falsetest_rename_goalText update200, goal.text updatedtest_empty_body_returns_200_noophas_updates() returns False → no-op200, goal unchangedtest_returns_404_for_nonexistentUUID validation404test_returns_404_for_different_userOwnership via parent priority JOIN404
TestDeleteGoalEndpoint
TestWhat it provesExpectedtest_delete_goal_successHappy path: goal removed from response200, goals array emptytest_returns_404_for_nonexistentUUID validation404test_returns_404_for_different_userOwnership enforcement404

Additional Tests (Minor Coverage — Add to test_pg_mutation_endpoints.py)
In TestUpdatePriorityEndpoint — add:
TestWhat it provesExpectedtest_empty_body_returns_200_noopEmpty {} → has_updates()=False → returns current state200, priority unchanged
In TestUpdateDeliverableEndpoint — add:
TestWhat it provesExpectedtest_empty_body_returns_200_noopEmpty {} → has_updates()=False → returns current state200, deliverable unchanged
In TestCreatePriorityRequest scope (can be in existing test_pg_mutation_endpoints.py or the new file):
TestWhat it provesExpectedtest_negative_weekly_hour_target_returns_422Pydantic gt=0 enforcement via APIPOST flexible priority with weekly_hour_target: -5 → 422

Key Implementation Details for Claude Code
Flexible priority creation in tests requires all three fields: weekly_hour_target, checkpoint_date, and initial_goal_text (on POST /priorities). The existing create_test_priority helper bypasses the API and inserts directly into DB, so it doesn't need initial_goal_text. But the create_test_goal helper should similarly insert directly via PgGoal model.
Goal response shape in the priorities response:
json{
  "goals": [
    { "id": "uuid", "text": "goal text", "achieved": false }
  ]
}
Note: the DB column is goal_text but the API response field is text (mapped in build_priorities_response).
Empty body behavior: All three update endpoints (priority, deliverable, goal) have has_updates() guard that returns current state on empty body. Tests should assert 200 status AND that the entity is unchanged (not just 200).

Acceptance Criteria

 pg_goals added to conftest.py TRUNCATE statement
 test_pg_goal_endpoints.py created with all 17 goal tests
 3 additional tests added to test_pg_mutation_endpoints.py (empty body priority, empty body deliverable, negative weekly_hour_target)
 All tests pass: pytest tests/integration/priority_guardian/ -v
 No changes to application code (router, models, db_models)


Unit Test vs Integration Test Boundary
This is an integration test briefing. All tests hit the FastAPI app via httpx.AsyncClient, exercise the full stack (Pydantic validation → router → SQLAlchemy → PostgreSQL). No mocking of DB or request parsing. This verifies the actual HTTP contract the widget relies on.