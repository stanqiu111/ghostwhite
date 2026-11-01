# Documentation

Start with the guide for the task you are doing. Current guides live here;
feature specifications and dated acceptance evidence live under `specs/`.

| Task | Guide |
| --- | --- |
| Install and run locally | [Project README](../README.md#running-locally), [environment example](../.env.example) |
| Understand the apps, FQIDs and request flow | [Architecture and workflow](../WORKFLOW.md) |
| Change a page, theme or layout | [Frontend guide](FRONTEND.md) |
| Use or extend an API | [API reference](API.md), running server `/api/docs/` |
| Connect two Ghostwhite nodes | [Node setup](NODE_SETUP.md) |
| Integrate a third-party social node | [Inbox protocol and flows](INBOX_API_FLOW.md) |
| Integrate cross-node live streams | [Live-stream protocol](FEDERATED_STREAMING.md) |
| Understand the live-room interface | [Live-room UI](LIVE_ROOM_UI.md) |
| Verify, review and ship a change | [Shipping guide](SHIPPING.md) |

## Specifications and evidence

- Federated streaming:
  [implementation plan and checklist](../specs/006-federated-streams/plan.md),
  [validation](../specs/006-federated-streams/validation.md).
- [Microphone commentary](../specs/005-stream-microphone/spec.md):
  [manual checks](../specs/005-stream-microphone/quickstart.md),
  [validation](../specs/005-stream-microphone/validation.md).
- [Earlier feature records](../specs/) remain as historical context. An unchecked
  acceptance task stays pending even when implementation tests pass.
- [Project constitution](../.specify/memory/constitution.md) defines code conventions;
  [CLAUDE.md](../CLAUDE.md) points to the active feature plan.

## Repository map

```text
README.md                  local setup and project overview
WORKFLOW.md                architecture and development flow
docs/                      current guides and integration protocols
specs/                     feature plans, tasks and dated validation
authors/, entries/, inbox/ application templates and static files
streams/                   live rooms, federation and media test harnesses
static/css/                shared design tokens, header and dark theme
static/js/                 shared navigation, API and Markdown libraries
```

The former root files `api_doc.md`, `INBOX_API_FLOW.md` and
`HEROKU_SHELL_COMMANDS.md` are now `API.md`, `INBOX_API_FLOW.md` and
`NODE_SETUP.md` in this directory. Node setup is local-first; it does not assume
a configured production deployment.
