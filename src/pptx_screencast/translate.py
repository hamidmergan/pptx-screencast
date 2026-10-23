"""Translating a finished narration with the chat model.

The script generation already writes in the target language, so this is for
the other way in: a script file or the speaker notes of a deck that are
already written and only need another language.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from .glossary import glossary_hint

logger = logging.getLogger(__name__)

TRANSLATE_PROMPT = (
    "You translate spoken narration scripts. Output MUST be in {language}. "
    "Translate the whole text and nothing else.\n"
    "Rules:\n"
    "- Keep all facts, numbers, names, dates, and links exactly as they are.\n"
    "- Keep the spoken, conversational tone and the order of the sentences.\n"
    "- NO semicolons, NO dashes - use only periods, commas, exclamation marks, "
    "and question marks.\n"
    "- Do NOT add, explain, or comment on anything.\n"
    "- Answer with the translation alone, no quotes and no heading.\n"
    "- Text that is already in {language} comes back unchanged."
)


class _TranslateMixin:
    """Expects client and model on the object."""

    def translate_text(
        self,
        text: str,
        target_lang: str,
        glossary: dict[str, str] | None = None,
    ) -> str:
        """One text in the target language, empty input stays empty.

        A glossary pins the terms, the same way it does when the narration is
        written, so a term does not change its wording on the way out.
        """
        if not text or not text.strip() or not (target_lang or "").strip():
            return text
        system_prompt = (
            glossary_hint(glossary)
            + TRANSLATE_PROMPT.replace("{language}", target_lang.strip())
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
                extra_body=self._extra_body or None,
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("The model returned no translation")
            return content.strip()
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"LLM API error: {e}") from e

    def translate_batch(
        self,
        texts: list[str],
        target_lang: str,
        max_workers: int | None = None,
        glossary: dict[str, str] | None = None,
    ) -> list[str]:
        """Every text on its own request, the order is kept.

        A text that cannot be translated keeps its original, a lost
        translation must not take the whole deck down with it.
        """
        if not texts:
            return []
        if max_workers is None:
            max_workers = self._batch_max_workers

        def _one(index_and_text: tuple[int, str]) -> str:
            index, text = index_and_text
            if not text.strip():
                return text
            try:
                return self.translate_text(text, target_lang, glossary)
            except Exception as e:
                logger.warning("Slide %s was not translated: %s", index + 1, e)
                return text

        work = list(enumerate(texts))
        workers = max(1, min(max_workers, len(work)))
        if workers == 1:
            return [_one(item) for item in work]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(_one, work))
