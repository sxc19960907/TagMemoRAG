# Public project website

## Goal

Create a public, install-free website for TagMemoRAG so visitors can understand the project, see what it does, and follow a practical guide without cloning or running the app.

## Requirements

- Build a static website that can be hosted on GitHub Pages.
- Include a project introduction, core capability overview, quick-start flow, operator guide, OCR notes, security/access notes, and links to the GitHub release/repository.
- Use polished, professional product documentation design, not an in-app admin page.
- Keep the site self-contained: static HTML/CSS/JS only, no build step required.
- Do not expose local paths, secrets, API keys, raw debug fields, or private runtime data.
- Add a GitHub Pages deployment workflow that publishes the static site directory.
- Keep the existing app runtime routes unchanged.
- Add lightweight tests/checks that verify the site files and workflow exist and contain the expected public guidance.

## Acceptance Criteria

- [x] Static site files render a public project introduction and guide without running TagMemoRAG.
- [x] The site includes clear navigation for overview, capabilities, quick start, user flow, admin flow, OCR, deployment, and FAQ.
- [x] The site is responsive and visually polished across desktop/mobile.
- [x] GitHub Pages workflow can publish the static site directory.
- [x] Tests cover the public site content and Pages workflow.
- [x] Existing focused UI/static tests remain green.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- The repository is currently private; GitHub Pages publication may require repository/settings support after the workflow is merged.
