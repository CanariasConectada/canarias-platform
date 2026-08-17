# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Odoo speaks locales ("es_ES"); every engine below wants a bare ISO-639-1 code.
# DeepL is the exception twice over: it upper-cases, and when translating *into*
# English or Portuguese it rejects the bare code and demands a regional variant.
DEEPL_TARGET_OVERRIDES = {"en": "EN-GB", "pt": "PT-PT"}

ANTHROPIC_VERSION = "2023-06-01"

TRANSLATOR_SYSTEM_PROMPT = (
    "You are a professional translator for a Canary Islands local-commerce "
    "marketplace. Translate each item from {source} into {target}. Keep the "
    "register warm and commercial. Preserve any HTML tags, placeholders and "
    "leading or trailing whitespace exactly as they appear. Never add "
    "commentary. Do not translate brand names, street names or product "
    "reference codes. Reply with a JSON array of strings, one per input item, "
    "in the same order and with the same length as the input."
)

ARBITER_SYSTEM_PROMPT = (
    "You are judging machine translations from {source} into {target} for a "
    "local-commerce marketplace. You will get the source texts and several "
    "candidate translations, each produced by a different engine. Pick the "
    "single best candidate overall, judging accuracy first, then fluency, then "
    "whether HTML and placeholders survived intact. Reply with only a JSON "
    'object {{"winner": <zero-based index>, "why": "<short reason>"}}.'
)


class AutoTranslateEngine(models.Model):
    """A configured translation service.

    Engines are records rather than a selection field on purpose: the platform
    is meant to run several at once, let a jury compare them and have an LLM
    arbiter pick the winner. That is impossible to express with a single
    setting, and adding a fifth provider later must not mean a migration.
    """

    _name = "auto.translate.engine"
    _description = "Automatic Translation Engine"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    engine_type = fields.Selection(
        [
            ("libretranslate", "LibreTranslate (self-hosted)"),
            ("google", "Google Cloud Translation"),
            ("deepl", "DeepL"),
            ("anthropic", "Claude (Anthropic)"),
        ],
        required=True,
        default="libretranslate",
    )
    endpoint_url = fields.Char(
        help="Base URL of the service. Leave empty to use the provider default."
    )
    api_key = fields.Char(
        groups="base.group_system",
        help="Not needed by a self-hosted LibreTranslate without key enforcement.",
    )
    model_name = fields.Char(
        default="claude-sonnet-5",
        help="LLM engines only: which model answers the request.",
    )
    timeout = fields.Integer(default=30, help="Seconds to wait for a reply.")
    in_jury = fields.Boolean(
        string="Takes part in the jury",
        help="In jury mode every engine ticked here translates the same text "
        "and the arbiter picks the best answer.",
    )
    is_arbiter = fields.Boolean(
        string="Can arbitrate",
        help="Only an LLM engine can judge other engines' output.",
    )
    last_error = fields.Char(readonly=True)

    _name_unique = models.Constraint(
        "UNIQUE (name)", "An engine with that name already exists."
    )

    @api.constrains("is_arbiter", "engine_type")
    def _check_arbiter_is_an_llm(self):
        for engine in self:
            if engine.is_arbiter and engine.engine_type != "anthropic":
                raise ValidationError(
                    self.env._(
                        "“%(name)s” cannot arbitrate: only an LLM engine can "
                        "compare translations and explain its choice.",
                        name=engine.name,
                    )
                )

    # ------------------------------------------------------------------
    # Language codes
    # ------------------------------------------------------------------
    def _engine_lang(self, odoo_lang, is_target=False):
        """Turn an Odoo locale into whatever this provider calls that language."""
        base = (odoo_lang or "").split("_")[0].split("@")[0].lower()
        if self.engine_type == "deepl":
            if is_target and base in DEEPL_TARGET_OVERRIDES:
                return DEEPL_TARGET_OVERRIDES[base]
            return base.upper()
        return base

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def translate(self, texts, source_lang, target_lang, is_html=False):
        """Translate ``texts`` and return a list of the same length.

        Length is part of the contract: callers zip the result back onto the
        terms they extracted, so a provider that silently drops an item would
        shift every following translation onto the wrong term.
        """
        self.ensure_one()
        if not texts:
            return []
        handler = getattr(self, "_translate_%s" % self.engine_type)
        result = handler(list(texts), source_lang, target_lang, is_html)
        if len(result) != len(texts):
            raise UserError(
                self.env._(
                    "“%(name)s” returned %(got)s translations for %(sent)s "
                    "texts; refusing to guess which is which.",
                    name=self.name,
                    got=len(result),
                    sent=len(texts),
                )
            )
        return result

    def action_test_connection(self):
        self.ensure_one()
        source = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.source_lang", "es_ES")
        )
        try:
            sample = self.translate(["Buenos días"], source, "en_US")
        except Exception as error:  # noqa: BLE001 - shown to the user verbatim
            self.last_error = str(error)[:255]
            raise UserError(
                self.env._(
                    "“%(name)s” did not answer: %(error)s", name=self.name, error=error
                )
            ) from error
        self.last_error = False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "“%(name)s” answered: %(sample)s", name=self.name, sample=sample[0]
                ),
            },
        }

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    def _post(self, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout or 30)
        response = requests.post(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def _translate_libretranslate(self, texts, source_lang, target_lang, is_html):
        url = "%s/translate" % (self.endpoint_url or "http://localhost:5000").rstrip(
            "/"
        )
        payload = {
            "q": texts,
            "source": self._engine_lang(source_lang),
            "target": self._engine_lang(target_lang, is_target=True),
            "format": "html" if is_html else "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        data = self._post(url, json=payload)
        translated = data.get("translatedText")
        # A single-item list comes back as a bare string on some builds.
        if isinstance(translated, str):
            return [translated]
        return translated or []

    def _translate_google(self, texts, source_lang, target_lang, is_html):
        url = (
            self.endpoint_url
            or "https://translation.googleapis.com/language/translate/v2"
        )
        data = self._post(
            url,
            params={"key": self.api_key},
            json={
                "q": texts,
                "source": self._engine_lang(source_lang),
                "target": self._engine_lang(target_lang, is_target=True),
                "format": "html" if is_html else "text",
            },
        )
        return [item["translatedText"] for item in data["data"]["translations"]]

    def _translate_deepl(self, texts, source_lang, target_lang, is_html):
        url = "%s/v2/translate" % (
            self.endpoint_url or "https://api-free.deepl.com"
        ).rstrip("/")
        payload = {
            "text": texts,
            "source_lang": self._engine_lang(source_lang),
            "target_lang": self._engine_lang(target_lang, is_target=True),
        }
        if is_html:
            payload["tag_handling"] = "html"
        data = self._post(
            url,
            headers={"Authorization": "DeepL-Auth-Key %s" % self.api_key},
            json=payload,
        )
        return [item["text"] for item in data["translations"]]

    def _translate_anthropic(self, texts, source_lang, target_lang, is_html):
        url = "%s/v1/messages" % (
            self.endpoint_url or "https://api.anthropic.com"
        ).rstrip("/")
        data = self._post(
            url,
            headers={
                "x-api-key": self.api_key or "",
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self.model_name or "claude-sonnet-5",
                "max_tokens": 8192,
                "system": TRANSLATOR_SYSTEM_PROMPT.format(
                    source=source_lang, target=target_lang
                ),
                "messages": [
                    {"role": "user", "content": json.dumps(texts, ensure_ascii=False)}
                ],
            },
        )
        return self._parse_json_reply(data, expect_list=True)

    def _parse_json_reply(self, data, expect_list=False):
        """Pull the JSON payload out of an Anthropic answer.

        Models sometimes wrap the array in a ```json fence even when told not
        to, and that would otherwise blow up as a decode error on a reply that
        is actually correct.
        """
        raw = "".join(
            block.get("text", "") for block in data.get("content", [])
        ).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        parsed = json.loads(raw)
        if expect_list and not isinstance(parsed, list):
            raise UserError(
                self.env._(
                    "The LLM answered with %(kind)s instead of a list.",
                    kind=type(parsed).__name__,
                )
            )
        return parsed

    # ------------------------------------------------------------------
    # Single engine or jury
    # ------------------------------------------------------------------
    @api.model
    def _run(self, texts, source_lang, target_lang, is_html=False):
        """Translate through whatever the platform is configured to use.

        Returns ``(translations, engine)`` so the caller can record which
        engine actually produced what shipped.

        Everything the glossary protects is fenced off here rather than in each
        engine, because this is the single funnel every translation goes
        through -- single engine and jury alike -- and a brand that slips past
        one engine is as wrong as a brand that slips past all of them. The
        request always leaves as HTML: that is the only format in which the
        guard survives the round trip. See
        :mod:`~.auto_translate_glossary` for the measurements behind that.
        """
        params = self.env["ir.config_parameter"].sudo()
        Glossary = self.env["auto.translate.glossary"]
        # What went out, so what comes back can be put right rather than
        # trusted: an engine is free to change the case of a guarded term, and
        # "&Nbsp;" is not the entity "&nbsp;", it is five visible characters.
        held = {}
        guarded = [
            Glossary._protect(text, is_html, held, target_lang) for text in texts
        ]

        if params.get_param("website_auto_translate.mode", "single") == "jury":
            jury = self.search([("in_jury", "=", True)])
            if len(jury) > 1:
                translated, engine = self._run_jury(
                    jury, guarded, source_lang, target_lang, True
                )
                return self._release(translated, target_lang, is_html, held), engine
        engine = self._default_engine()
        translated = engine.translate(guarded, source_lang, target_lang, True)
        return self._release(translated, target_lang, is_html, held), engine

    @api.model
    def _release(self, texts, target_lang, is_html, held=None):
        Glossary = self.env["auto.translate.glossary"]
        return [Glossary._restore(text, target_lang, is_html, held) for text in texts]

    @api.model
    def _default_engine(self):
        params = self.env["ir.config_parameter"].sudo()
        engine_id = params.get_param("website_auto_translate.engine_id")
        engine = self.browse(int(engine_id)) if engine_id else self.browse()
        if not engine.exists() or not engine.active:
            engine = self.search([], limit=1)
        if not engine:
            raise UserError(self.env._("No translation engine is configured."))
        return engine

    @api.model
    def _run_jury(self, jury, texts, source_lang, target_lang, is_html):
        """Ask every juror, then let the arbiter pick a winner.

        A juror that fails is dropped rather than fatal -- the point of running
        several engines is that one being down should not stop the platform
        translating.
        """
        candidates = []
        for juror in jury:
            try:
                candidates.append(
                    (juror, juror.translate(texts, source_lang, target_lang, is_html))
                )
            except (
                Exception
            ) as error:  # noqa: BLE001 - one juror must not sink the jury
                juror.last_error = str(error)[:255]
                _logger.warning("Juror %s failed: %s", juror.name, error)
        if not candidates:
            raise UserError(self.env._("Every engine in the jury failed."))
        if len(candidates) == 1:
            return candidates[0][1], candidates[0][0]
        arbiter = self.search([("is_arbiter", "=", True)], limit=1)
        if not arbiter:
            return candidates[0][1], candidates[0][0]
        index = arbiter._pick_winner(texts, candidates, source_lang, target_lang)
        return candidates[index][1], candidates[index][0]

    def _pick_winner(self, texts, candidates, source_lang, target_lang):
        """Return the index of the best candidate, falling back to the first."""
        self.ensure_one()
        question = {
            "source_texts": texts,
            "candidates": [
                {"index": position, "engine": juror.name, "translation": translation}
                for position, (juror, translation) in enumerate(candidates)
            ],
        }
        try:
            data = self._post(
                "%s/v1/messages"
                % (self.endpoint_url or "https://api.anthropic.com").rstrip("/"),
                headers={
                    "x-api-key": self.api_key or "",
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_name or "claude-sonnet-5",
                    "max_tokens": 1024,
                    "system": ARBITER_SYSTEM_PROMPT.format(
                        source=source_lang, target=target_lang
                    ),
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps(question, ensure_ascii=False),
                        }
                    ],
                },
            )
            verdict = self._parse_json_reply(data)
            winner = int(verdict["winner"])
        except (
            Exception
        ) as error:  # noqa: BLE001 - a silent arbiter must not block the queue
            _logger.warning(
                "Arbiter %s failed, keeping the first candidate: %s", self.name, error
            )
            return 0
        if not 0 <= winner < len(candidates):
            _logger.warning("Arbiter %s picked %s, out of range", self.name, winner)
            return 0
        return winner
