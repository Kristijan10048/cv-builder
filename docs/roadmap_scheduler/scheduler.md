## Scheduler implementation
 - Create a roadmap for implementing Task scheduler service for the CV Builder application
 - For each task in the roadmap create a separate file .md file.
 - In each file introduce dependency to the other tasks. The goal is to be able to execute the tasks in parallel.
 - Implement task scheduler service
 - The service should be ruining independently
 - It should be possible to add scheduled tasks
 - Currently there will be tasks for fetching jobs from different web sites
 - There might be other tasks in the future
 - Ask questions when something is not clear
 - Also include in the roadmap refactoring strategy for the UI and for the back end part.
 - Create the roadmap and task files only. Do not implement application code yet.
 - Also include suggestions how to split and immanent the tasks which are independent with coding agents such as codex cli.
 - Use APScheduler library

## Planning deliverables

Original scope on 2026-10-31 was planning only. On 2026-11-03 the user authorized
implementation in a single pass. The scheduler is now implemented and verified;
see [verification.md](verification.md) and [operations](../scheduler_operations.md).

- [Scheduler development roadmap](scheduler_roadmap.md)
- [Coding-agent execution guide](coding_agent_execution.md)
- Individual implementation tickets are linked from the roadmap, with dependencies,
  file ownership, acceptance criteria, and validation for each task.
