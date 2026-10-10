# Python Code
    - Coding Conventions & Style Guide 
    - One statement per line
    - Explicit code
    - Create classes. Use object oriented style
    - Do not hardcode sql queries
    - Include description for every function and class
    - Write comments for important code such as logic
    - do not use short names for variables, functions or classes.
    - prefix constants with C_ for example C_PI=3.14
    - use PascalCase for class names
    - Create a model class for each db table
    - Do not hardcode strings or numbers in the code use C_<NAME> = Value

# NodeJs Code
    ## Environment & Commands
    Always use these exact commands when testing or validating code:
    - **Install dependencies:** `pnpm install`
    - **Run local development:** `pnpm dev`
    - **Execute unit tests:** `pnpm test`
    - **Lint code:** `pnpm lint`
    - **Database migration:** `pnpm prisma migrate dev`

    ## Coding Conventions & Style Guide
    - **TypeScript:** Enforce strict type safety. Avoid using `any`.
    - **Formatting:** Use single quotes, no semicolons, and 2-space indentation.
    - **Components:** Prefer functional components with explicit prop types. 
    - **File Naming:** Use kebab-case for assets/utilities (`date-helper.ts`) and PascalCase for React components (`Button.tsx`).

    ## Critical Safety Boundaries
    - **Environment Variables:** Never hardcode secrets. Always read from `process.env`.
    - **Database:** Do not drop tables or run destructive sync commands without explicit confirmation.
    - **API Keys:** Never commit API keys or expose private tokens to client-side code.
