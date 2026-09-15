"""Small Kinyarwanda <-> English keyword map for code-switched queries.

Rwandan readers mix English (and French) into Kinyarwanda constantly. The
retriever expands every content term with its translations so "football
results" still lands on "umupira w'amaguru" articles and vice versa. This is
a lexical aid only — proper nouns are language-neutral substrings anyway.
Keys and values are lowercase single tokens (apostrophes already split).
"""

from __future__ import annotations

KI_EN: dict[str, tuple[str, ...]] = {
    # state & politics
    "perezida": ("president",),
    "minisitiri": ("minister",),
    "guverinoma": ("government",),
    "leta": ("government", "state"),
    "inteko": ("parliament",),
    "urukiko": ("court",),
    "inkiko": ("courts",),
    "polisi": ("police",),
    "ingabo": ("army", "military"),
    "umutekano": ("security",),
    "amatora": ("elections", "election"),
    "amajwi": ("votes",),
    "ambasaderi": ("ambassador",),
    "umuyobozi": ("leader", "director", "official"),
    "abayobozi": ("leaders", "officials"),
    "uruzinduko": ("visit",),
    "inama": ("meeting", "summit"),
    "amasezerano": ("agreement", "deal"),
    "ubutabera": ("justice",),
    "ruswa": ("corruption",),
    "iperereza": ("investigation",),
    "gereza": ("prison",),
    "imfungwa": ("prisoners",),
    "jenoside": ("genocide",),
    "amahoro": ("peace",),
    "intambara": ("war",),
    "impunzi": ("refugees",),
    # economy
    "ubukungu": ("economy",),
    "ubucuruzi": ("trade", "business"),
    "imisoro": ("taxes", "tax"),
    "ibiciro": ("prices", "price"),
    "igiciro": ("price",),
    "amafaranga": ("money",),
    "ifaranga": ("franc", "currency"),
    "banki": ("bank",),
    "inguzanyo": ("loan",),
    "ishoramari": ("investment",),
    "abashoramari": ("investors",),
    "akazi": ("jobs", "employment"),
    "umushahara": ("salary",),
    "ubukene": ("poverty",),
    "ubuhinzi": ("agriculture", "farming"),
    "abahinzi": ("farmers",),
    "ubworozi": ("livestock",),
    "ikawa": ("coffee",),
    "icyayi": ("tea",),
    "inzara": ("hunger", "famine"),
    "ubukerarugendo": ("tourism",),
    # health & education
    "ubuzima": ("health",),
    "indwara": ("disease", "illness"),
    "urukingo": ("vaccine",),
    "inkingo": ("vaccines",),
    "ibitaro": ("hospital",),
    "abaganga": ("doctors",),
    "uburezi": ("education",),
    "ishuri": ("school",),
    "amashuri": ("schools",),
    "abanyeshuri": ("students",),
    "kaminuza": ("university",),
    "abarimu": ("teachers",),
    # sport
    "umupira": ("football", "soccer"),
    "amaguru": ("football",),
    "ikipe": ("team", "club"),
    "amakipe": ("teams", "clubs"),
    "umukino": ("match", "game"),
    "imikino": ("games", "sports"),
    "siporo": ("sports", "sport"),
    "shampiyona": ("league", "championship"),
    "igikombe": ("cup",),
    "umutoza": ("coach",),
    "umukinnyi": ("player",),
    "abakinnyi": ("players",),
    "ikibuga": ("stadium",),
    # environment & infrastructure
    "ikirere": ("weather", "climate"),
    "imvura": ("rain",),
    "umwuzure": ("flood", "floods"),
    "umutingito": ("earthquake",),
    "inkongi": ("fire",),
    "impanuka": ("accident",),
    "umuhanda": ("road",),
    "imihanda": ("roads",),
    "ikiraro": ("bridge",),
    "amashanyarazi": ("electricity", "power"),
    "amazi": ("water",),
    "inyubako": ("building",),
    "ubwikorezi": ("transport",),
    "indege": ("plane", "flight", "aircraft"),
    "ikinyabiziga": ("vehicle",),
    "ingagi": ("gorillas",),
    "inyamaswa": ("animals", "wildlife"),
    # tech, media, culture
    "ikoranabuhanga": ("technology", "tech"),
    "interineti": ("internet",),
    "telefoni": ("phone",),
    "itangazamakuru": ("media", "press"),
    "umunyamakuru": ("journalist",),
    "abanyamakuru": ("journalists",),
    "umuziki": ("music",),
    "umuhanzi": ("artist", "musician"),
    "abahanzi": ("artists", "musicians"),
    "filime": ("film", "movie"),
    "idini": ("religion",),
    "kiliziya": ("church",),
    # people & places
    "umugore": ("woman",),
    "abagore": ("women",),
    "urubyiruko": ("youth",),
    "abana": ("children",),
    "umujyi": ("city",),
    "umudugudu": ("village",),
    "intara": ("province",),
    "akarere": ("district",),
    "uturere": ("districts",),
    "uburayi": ("europe",),
    "amerika": ("america", "usa"),
    "ubushinwa": ("china",),
    "ubufaransa": ("france",),
    "ubwongereza": ("britain", "england"),
    "ubudage": ("germany",),
    "ubuhinde": ("india",),
    "uburusiya": ("russia",),
    "tanzaniya": ("tanzania",),
    "ubugande": ("uganda",),
    "kongo": ("congo", "drc"),
    "afurika": ("africa",),
    "isi": ("world",),
    "loni": ("united nations",),
    # events
    "urupfu": ("death",),
    "yapfuye": ("died",),
    "ubukwe": ("wedding",),
    "ubujura": ("theft",),
}

EN_KI: dict[str, tuple[str, ...]] = {}
for _ki, _ens in KI_EN.items():
    for _en in _ens:
        for _tok in _en.split():
            EN_KI.setdefault(_tok, ())
            if _ki not in EN_KI[_tok]:
                EN_KI[_tok] = EN_KI[_tok] + (_ki,)


def translations(term: str) -> list[str]:
    """Cross-language alternates for a lowercase token (may be empty)."""
    out: list[str] = []
    for alt in KI_EN.get(term, ()) + EN_KI.get(term, ()):
        for tok in alt.split():
            if tok != term and tok not in out:
                out.append(tok)
    return out
