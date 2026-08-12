Gives the auth page something honest to say while it waits.

Three affordances, each on its own clock, because they answer different
questions:

- **The pressed button goes busy immediately.** A ring appears in front of the
  label the button already had, the control is disabled a tick later, and the
  original wording is kept — which is what makes it correct on login, signup,
  password reset and guest entry alike without guessing at a verb. This is also
  the real double-submit guard.
- **A thin top bar** reports the boot wait: the window between the page being
  painted and the lazy JavaScript bundle being ready.
- **A full curtain** appears only after 200 ms and then stays for at least
  400 ms. Fast responses never raise it at all, and one that did flash for
  20 ms would read as a glitch rather than as feedback.

Everything is inlined into the page. Nothing here is added to
`web.assets_frontend`, and that is the whole design: a loader delivered inside
the 1.1 MB stylesheet whose wait it reports on can only ever appear once the
waiting is over.

Nothing is shown by JavaScript that is not also removable by it. The curtain is
rendered `hidden` and only the script reveals it, so a visitor whose browser
never runs the script sees the plain form rather than a cover nobody is left to
lift.
