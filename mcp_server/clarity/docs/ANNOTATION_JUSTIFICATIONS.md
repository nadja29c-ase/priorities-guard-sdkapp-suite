# Tool Annotation Justifications

This document provides justification for each tool's annotations as required for OpenAI SDK app submission.

| Tool | readOnlyHint | destructiveHint | openWorldHint | Justification |
|------|--------------|-----------------|---------------|---------------|
| organize_thoughts | false | false | false | Creates ephemeral in-memory board state. No persistent storage until user explicitly calls save_board. |
| load_saved_board | true | false | false | Read-only retrieval of persisted data. No mutations to stored state. |
| read_saved_board | true | false | false | Read-only data fetch for LLM merge operations. No mutations. |
| save_board | false | true | false | Overwrites user's previously saved board. Destructive to prior persisted state. |
| prioritize_clusters | false | false | false | Modifies ephemeral priority assignments in working board. Not destructive — changes are reversible and not persisted until explicit save. |
| edit_board | false | true | false | Contains delete operations (clusters, subclusters, thought items). Destructive to working board state. |
| delete_my_data | false | true | false | Permanently deletes all user data from database. Irreversible. |

## Notes

- **readOnlyHint**: Set to `true` only for tools that have zero side effects and are safe to retry.
- **destructiveHint**: Set to `true` for any tool that overwrites or deletes user data.
- **openWorldHint**: Set to `false` for all tools — Clarity only interacts with its own backend, not external systems.
