 ## Create a Python script to start the application services
  - The script should have generic implementation:
    - For now there are only two services in the app, however in the future more services can be added
  - The script should be compatible with docker.
    - In case where the app will be running inside docker a container
  - Script parameters:
    - The script should have flags to: Start, stop and restart a specific service.
    - It should be possible with a single command to start, stop and restart all services also
    - The script should have a -status flag so that it will display the statuses of the running services
  - Make a small implementation plan and write it in this folder. Do not implement it yet.
    - The plan should include short summary abut implementation steps.

---
#### Update 17.11.2026:
 1. CLI improvements
    - CLI  terminal look
      - Luncher should display in the title current git commit hash
      - Launcher should include colors for status labels. This should be generic behavior in case where other services are added:
        - Yellow for stopped
        - Green for running
        - Red for failed to start
      - After looking at the CLI improvements update the plan accordingly
        - Always append the plan .md file at the edn/bottom of the file when possible
        - Include timestamp
      - Include in the plan graphical CLI preview
        - In the preview include printing git commit hash
      - When the plan is ready we can continue with implementation
      - In case some points are not clear feel free to ask questions and update the plan
