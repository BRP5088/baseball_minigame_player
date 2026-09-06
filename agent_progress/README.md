# agent_progress/

One directory per subagent, written WHILE it works. Not project data. Ignored by
git, safe to delete wholesale at any time.

## Why this exists

On 2026-09-05 four parallel workflows hit a usage limit mid-flight. Eighteen
agents were killed. One of them had spent 179 tool calls and twelve minutes
reading archived frames, and returned nothing at all — its findings existed only
in a context that no longer exists.

An agent that is killed loses everything it has not written down. Nothing about
that is recoverable afterwards: the transcript holds the tool calls but not the
conclusion, and re-running costs the same tokens again.

## The layout

    agent_progress/<your-label>/
        progress.md      the notes below — REQUIRED, written first
        *.py             any script you wrote to get an answer
        *.json *.csv     data you extracted
        *.png            plots

A DIRECTORY, not a single file, for two reasons. Scripts and plots have nowhere
else to live: CLAUDE.md forbids findings in /tmp, and /tmp on this machine was
once found as 825 empty directories with every file gone. And an agent that
writes several artefacts cannot collide with another agent's.

The script that produced a number belongs next to the number. Re-deriving a
statistic later, from prose alone, is how a wrong one survives.

## The rule

Write `agent_progress/<your-label>/progress.md` on your FIRST tool call, and
update it every few tool calls. Cheap and repetitive beats complete and never
written — a file written when you finish is lost in precisely the case it is
for.

## What progress.md holds

    # <label>
    ## Task
    one line — what you were asked for

    ## Established
    facts you have VERIFIED, each with the file or command that verified it

    ## Assumed
    anything you are working from but have NOT checked

    ## Open
    what you were about to do next

Keep `Established` and `Assumed` apart. A half-finished analysis restored later
reads exactly as authoritative as a finished one, and this project has lost days
to output that looked like evidence and was not.

If you are resuming, READ your own directory first — and re-verify anything
under `Assumed` before building on it.

## Note on the 2026-09-05 run

The six ticket agents from that day predate this layout and wrote flat
`<label>.md` files at the top level. They were left alone rather than migrated
mid-write. Anything after that uses the directory form.
