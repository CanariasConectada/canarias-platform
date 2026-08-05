## Turning moderation on

1. Go to **Discuss > Moderation > Moderated Channels** and create a
   configuration for the channel.
2. Choose who is held: **Moderate Guests** (on by default) and/or **Moderate
   Portal Users** (off by default). Internal users are never held.
3. List the **Moderators**. Only the users listed here see this channel's
   queue; a moderator of another channel does not.

To stop moderating a channel, archive its configuration: the history of past
decisions is preserved.

> **Read this before calling a channel "moderated".** With **Moderate Portal
> Users** off — the default — a visitor who creates an account posts straight
> through, with no review at all. On a site with self-signup enabled, that is
> one click away, and it is the intended behaviour: registering is how a
> visitor takes responsibility for what they publish. So "moderated channel"
> means "moderated for anonymous visitors" unless you turn that switch on. Say
> so wherever you promise moderation to your users.

## What is held, beyond the message text

- **Files** are not channel attachments until approval — they are not listed
  by the channel's Attachments panel and cannot be downloaded, but you can open
  them from the held message to decide. Their author can no longer delete them
  while they are held, so nobody can empty the evidence out from under you.
- **Editing an approved message** unpublishes it and sends the new text back to
  your queue. Readers see a removed message meanwhile; approving the edit posts
  it again.
- **Reactions** must be a single emoji, and **guest names** are stripped of any
  markup and shortened, so the byline next to a message cannot become a message
  of its own.
- **Threads opened under a moderated channel** are moderated too, and their
  held messages arrive in the parent channel's queue.
- **"Started a call" notices** are dropped rather than queued. Approving one
  later would announce a call that has already ended.

## What moderation costs on the channel

- **Link previews are switched off.** No message on a moderated channel gets a
  rich card, not even one posted by you. A preview is fetched from someone
  else's server and its image is re-fetched by every reader's browser
  afterwards, so it is content nobody can approve once and for all. Links still
  render and still work.
- **Rate limiting is not covered.** A persona is capped at 64 KB per message
  and 20 undecided messages per channel, and nothing else stands between a
  determined flooder and your queue.
- **Portal users are not held by default.** See the warning above.

## Working the queue

**Discuss > Moderation > Pending Messages** shows the held comments of the
channels you moderate, grouped by channel. Approve publishes the message on
the channel, attributed to its original author (a guest stays a guest).
Reject discards it — no message is ever created — and the reason you type is
pushed to the author.

Both actions are idempotent: deciding an already-decided message does nothing.

**Discuss > Moderation > History** shows every decision, including the
approved messages and the reasons given for the rejected ones. Held messages
cannot be created or deleted from the backend: the history is immutable.

## Front-end integration

The module pushes three bus notifications a JS client can listen to:

- `discuss.channel.moderation/author_status` — sent to the *author* every time
  their message is held, approved or rejected. Use it to render a "waiting for
  moderation" placeholder and, on rejection, the reason.
- `discuss.channel.moderation/new_pending` — sent to every moderator of the
  channel when a new message lands in the queue.

The payload is `{id, channel_id, state, author_name, rejection_reason,
message_id}`.
