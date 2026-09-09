## Publishing a channel on the chat page

Discuss > a channel > **En el chat de la web**. Nothing else changes: who may
read and post is still the channel's own group, so publishing a closed channel
puts it on the list only for the people who could already open it.

## Answering the support conversations

Every visitor who opens **Hablar con soporte** gets a private conversation of
their own, and it lands in the Discuss sidebar of everybody who answers.
Administrators are there automatically. To add somebody who is *not* an
administrator, tick **Soporte: atender a los visitantes** on their user form
(Settings > Users, under Website).

Roles are gone: until 2026-09-09 the platform ran `base_user_role`, every
`res.users` write re-derived the user's groups from their roles, and the
group had to be granted through the role *Soporte (chat de visitantes)*.
The roles were retired and permissions are managed per user; the group on
the form is the grant that lasts.

Somebody appointed today joins the conversations that were already waiting:
the nightly cron *Chat: sentar a los agentes de soporte en las conversaciones
abiertas* seats every current agent in every open conversation, and opening a
conversation seats them too. Nobody has to be appointed before the queue
starts, only before it is answered.

Removing the role removes them from nothing: they stay in the conversations
they were already seated in, which is deliberate — a conversation somebody has
been replying to should not lose its history holder. Remove them from the
channel members if that is what is wanted.

## What support conversations are not

They are never on the public channel list, they cannot be published there
(`website_chat_published` stays false), and they are `channel_type = "group"`
so only their members can read them. A visitor who guesses another
conversation's URL gets a 404, not an empty page.
