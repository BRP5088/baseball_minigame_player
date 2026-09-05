# agent_progress/

Scratch notes written BY subagents WHILE they work. Not project data. Ignored by
git, safe to delete wholesale at any time.

## Why this exists

On 2026-09-05 four parallel workflows hit a usage limit mid-flight. Eighteen
agents were killed. One of them had spent 179 tool calls and twelve minutes
reading archived frames, and returned nothing at all — its findings existed only
in a context that no longer exists.

An agent that is killed loses everything it has not written down. Nothing about
that is recoverable afterwards: the transcript holds the tool calls but not the
conclusion, and re-running costs the same tokens again.

## The rule

Write to `agent_progress/<your-label>.md` **as you go**, not at the end. A file
written when you finish is lost in precisely the case it is for.

Update it whenever you establish something, roughly every few tool calls. Cheap
and repetitive beats complete and never written.

## What to write

    # <label>
    ## Task
    one line — what you were asked for

    ## Established
    facts you have VERIFIED, each with the file/command that verified it

    ## Assumed
    anything you are working from but have NOT checked

    ## Open
    what you were about to do next

Keep `Established` and `Assumed` apart. A half-finished analysis restored later
reads exactly as authoritative as a finished one, and this project has lost days
to output that looked like evidence and was not.

If you are resuming, READ your own file first — and re-verify anything under
`Assumed` before building on it.
