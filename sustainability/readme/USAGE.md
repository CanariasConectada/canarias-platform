As an evaluator (internal user with the Sustainability User group):

1. Open the **Sostenibilidad** app and go to *My Evaluations*.
2. Click **New**: the cooldown is validated and the questionnaire opens in a
   new tab. Finish it to see your score, the awarded badge and a summary of
   improvement recommendations.
3. The badge appears automatically on your company microsite and in the
   public directory once awarded, and disappears when it expires.

As a manager:

* Review every evaluation under *Sostenibilidad > My Evaluations* (managers
  see all companies).
* To fix a score, call `action_override_score` from the evaluation (or use
  a server action): the original score, author, date and reason are kept in
  the *Audit* tab and the override survives recomputations.
* Public information pages are served at `/sostenibilidad` and
  `/sostenibilidad/instrucciones`.
