# pkg-cuhksz
## Why you'd want this
Compliance basis and usage rules: [COMPLIANCE.md](COMPLIANCE.md) — own-credential read-only pulls inside CUHK-SZ ITSO rules; personal-study use, no bulk crawls.

Course operations on autopilot for CUHK-SZ students: courseware, deadlines, announcements and grades pulled from Blackboard and SIS into the wiki, with a per-course cognition profile.

- Stop scraping portals — deadlines and announcements arrive as inbox pages; files map to course pages automatically
- The cognition profile tracks what you actually know per course, so teach/quiz target the gaps instead of re-explaining the familiar
- Read-only connectors; credentials stay local; enrollment data never enters any repository


vault-wiki domain package **cuhksz** — see [PKG.yaml](PKG.yaml) for members/connectors/compat; mechanism in the [framework](https://github.com/owfadev/owfa) (.meta/docs/packages.md).
