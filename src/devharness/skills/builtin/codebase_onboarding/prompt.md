# Codebase Onboarding

You are onboarding to a new codebase. Your goal is to understand the project
deeply enough to work on it effectively, then produce an architecture summary
as an artifact.

## Phase 1: Orientation

1. **Read the README.** Start with README.md (or equivalent) to understand the
   project's purpose, setup instructions, and high-level architecture.
2. **Check configuration files.** Read pyproject.toml, package.json, Cargo.toml,
   go.mod, or whichever package manifest exists. Note dependencies, build
   scripts, and tool configuration.
3. **Read AGENTS.md** if it exists. This contains project-specific instructions
   for agents.

## Phase 2: Structure

4. **Map the directory structure.** List the top-level directories and understand
   what each one contains (source code, tests, configs, docs, etc.).
5. **Identify entry points.** Find main files, app entry points, CLI definitions,
   or route registrations. Read them to understand how the application starts.
6. **Identify the data model.** Look for model definitions, database schemas,
   or type definitions that define the core domain.

## Phase 3: Architecture

7. **Trace a request or workflow.** Pick one key user-facing feature and trace
   its path through the codebase from entry point to data store. This reveals
   the architectural pattern (MVC, hexagonal, etc.).
8. **Identify key abstractions.** Find the main interfaces, base classes, or
   protocols that the codebase is built around.
9. **Check the test structure.** Read a few test files to understand testing
   patterns, fixtures, and coverage approach.

## Phase 4: Output

10. **Produce an architecture summary artifact** with:
    - Project purpose (one paragraph)
    - Tech stack (language, framework, key libraries)
    - Directory map with descriptions
    - Key abstractions and their relationships
    - Data flow for one key feature
    - Testing approach
    - Build/deploy pipeline overview
    - Known patterns and conventions

## Constraints

- Do not modify any files during onboarding.
- Read broadly but efficiently -- skim large files, focus on signatures and
  structure rather than implementation details.
- If the codebase is large, focus on the most important modules first.
- Produce the architecture summary as a `summary` artifact when done.
