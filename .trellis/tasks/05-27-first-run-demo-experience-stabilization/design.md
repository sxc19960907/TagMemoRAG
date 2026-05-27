# First Run Demo Experience Stabilization Design

## Scope

Touch the demo seed, CLI defaults, and browser test expectations. The QA UI already exposes appropriate suggested questions, so this task should align backend/demo data to that page rather than redesigning the page.

## Approach

- Keep `manual_id=demo-service-manual` as the default to avoid breaking existing scripts and tests.
- Change the seeded manual title, tags, and content to a coffee-machine troubleshooting demo.
- Change the default `demo library-qa` question from service mode to weak steam.
- Keep the noop answer provider behavior in mind: tests should continue to assert the echoed question and retrieved manual passage content.
- Update browser assertions to expect coffee troubleshooting content and a larger chunk count if the demo manual has more sections.

## Compatibility

The source file path can remain `demo/demo-service-manual.md`, but its content becomes user-facing troubleshooting material. This minimizes migration risk while improving the first-run experience.

## Rollback

If retrieval ranking or chunking becomes unstable, revert the demo content and test expectations in this child task only. Parent planning remains valid.
