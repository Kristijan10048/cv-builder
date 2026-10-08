# AGENTS.md

## 🚀 Tech Stack & Project Context
- **Framework:** Next.js 15 (App Router), React 19, TypeScript.
- **Database:** Prisma ORM with PostgreSQL.
- **Style:** Tailwind CSS, Shadcn/ui components.

## 🛠️ Environment & Commands
Always use these exact commands when testing or validating code:
- **Install dependencies:** `pnpm install`
- **Run local development:** `pnpm dev`
- **Execute unit tests:** `pnpm test`
- **Lint code:** `pnpm lint`
- **Database migration:** `pnpm prisma migrate dev`

## 🎨 Coding Conventions & Style Guide
- **TypeScript:** Enforce strict type safety. Avoid using `any`.
- **Formatting:** Use single quotes, no semicolons, and 2-space indentation.
- **Components:** Prefer functional components with explicit prop types. 
- **File Naming:** Use kebab-case for assets/utilities (`date-helper.ts`) and PascalCase for React components (`Button.tsx`).

## 🛡️ Critical Safety Boundaries
- **Environment Variables:** Never hardcode secrets. Always read from `process.env`.
- **Database:** Do not drop tables or run destructive sync commands without explicit confirmation.
- **API Keys:** Never commit API keys or expose private tokens to client-side code.

## 🏁 Definition of Done (Quality Gates)
Before completing any task or marking it resolved, you must:
1. Run `pnpm lint` and fix all warnings.
2. Run `pnpm test` to ensure no existing tests are broken.
3. Ensure the code compiles via `pnpm build`.
