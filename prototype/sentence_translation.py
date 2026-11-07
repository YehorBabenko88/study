"""Sentence translator with optional local Argos Translate backend.

Never invent translations when the language pack is absent.
"""
import re

LANGS = {"de", "ru"}
MAX_CHARS = 3000

def translate(text, source, target):
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_CHARS:
        raise ValueError("Enter 1–3000 characters")
    if source not in LANGS or target not in LANGS or source==target:
        raise ValueError("Choose distinct German/Russian languages")
    try:
        from argostranslate import translate as argos
    except ImportError:
        return {"status":"unavailable","reason":"argos_package_missing",
                "translation":None,"source":source,"target":target}
    languages = {x.code:x for x in argos.get_installed_languages()}
    if source not in languages or target not in languages:
        return {"status":"unavailable","reason":"language_pack_missing",
                "translation":None,"source":source,"target":target}
    try:
        model=languages[source].get_translation(languages[target])
        result=model.translate(text)
    except Exception:
        return {"status":"unavailable","reason":"translation_model_unavailable",
                "translation":None,"source":source,"target":target}
    return {"status":"ok","translation":result,"source":source,"target":target,
            "provider":"argos_local","review_status":"machine_translation_unverified"}

def split_words(text):
    if not isinstance(text,str) or len(text)>MAX_CHARS:
        raise ValueError("Invalid text")
    return re.findall(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*",text,flags=re.UNICODE)
