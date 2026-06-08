Design a production-grade web application for project and issue tracking, modeled 1:1 on Linear (linear.app) — the keyboard-first, minimal, fast issue tracker used by software teams.

Aesthetic: dark theme, near-black background (#0d0e10 with #090a0c panels), hairline borders (#23252a), indigo accent (#5e6ad2), compact system/UI typography (13-14px), dense but calm spacing, subtle hover highlights, minimal shadows. The feel is precise, quiet, and developer-grade — never a generic admin template.

Primary screen — the Issues view:

- Left sidebar (about 240px): workspace switcher at the top; primary nav (Inbox, My Issues); a "Workspace" section (Initiatives, Projects, Views); and a "Your teams" section listing a team ("Engineering") expanding to Issues, Cycles, and Projects.
- Top toolbar: the view title ("All issues"), a Filter control, a List/Board view switcher, Display options (group-by, ordering), and a search affordance.
- The issues list, grouped into collapsible status sections — Backlog, Todo, In Progress, Done, Canceled — each header showing a count. Every issue row shows: a priority icon (Urgent/High/Medium/Low/None), a status icon, the issue identifier (e.g. ENG-128), the title, inline colored label chips, an assignee avatar, and an estimate. Rows have clear hover and selected states.

Also represent these Linear screens and states in the design: a Board (Kanban) view with status columns and draggable issue cards; an issue detail right-panel (title, markdown description, a properties sidebar with Status, Priority, Assignee, Labels, Project, Cycle, Estimate, plus sub-issues and an activity/comments thread); a Command Palette (Cmd+K) overlay with searchable actions; and a Cycle view header with a scope/progress bar.

Convey real functionality through interactive affordances: status and priority dropdown menus, a "New issue" primary action, filter chips, keyboard-shortcut hints, and clear empty/hover/active states. Maintain WCAG AA contrast on the dark theme. Make it look and behave like the real Linear.
