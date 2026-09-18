# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""Offline phonetic suggestions, not translation or a language model.

Common words have curated spellings. Unknown Roman words use deterministic
letter rules; users must review names. No network or third-party dependency.
"""
import re

RASHIS = [
    'Mesha / ಮೇಷ', 'Vrishabha / ವೃಷಭ', 'Mithuna / ಮಿಥುನ',
    'Karkataka / ಕರ್ಕಾಟಕ', 'Simha / ಸಿಂಹ', 'Kanya / ಕನ್ಯಾ', 'Tula / ತುಲಾ',
    'Vrischika / ವೃಶ್ಚಿಕ', 'Dhanu / ಧನು', 'Makara / ಮಕರ',
    'Kumbha / ಕುಂಭ', 'Meena / ಮೀನ',
]
NAKSHATRAS = [
    'Ashwini / ಅಶ್ವಿನಿ', 'Bharani / ಭರಣಿ', 'Krittika / ಕೃತ್ತಿಕಾ',
    'Rohini / ರೋಹಿಣಿ', 'Mrigashira / ಮೃಗಶಿರ', 'Ardra / ಆರ್ದ್ರ',
    'Punarvasu / ಪುನರ್ವಸು', 'Pushya / ಪುಷ್ಯ', 'Ashlesha / ಆಶ್ಲೇಷಾ',
    'Magha / ಮಘಾ', 'Purva Phalguni / ಪೂರ್ವ ಫಲ್ಗುಣಿ', 'Uttara Phalguni / ಉತ್ತರ ಫಲ್ಗುಣಿ',
    'Hasta / ಹಸ್ತ', 'Chitra / ಚಿತ್ರಾ', 'Swati / ಸ್ವಾತಿ', 'Vishakha / ವಿಶಾಖಾ',
    'Anuradha / ಅನುರಾಧಾ', 'Jyeshtha / ಜ್ಯೇಷ್ಠಾ', 'Mula / ಮೂಲ',
    'Purva Ashadha / ಪೂರ್ವಾಷಾಢಾ', 'Uttara Ashadha / ಉತ್ತರಾಷಾಢಾ',
    'Shravana / ಶ್ರವಣ', 'Dhanishta / ಧನಿಷ್ಠಾ', 'Shatabhisha / ಶತಭಿಷಾ',
    'Purva Bhadrapada / ಪೂರ್ವಭಾದ್ರಪದ', 'Uttara Bhadrapada / ಉತ್ತರಭಾದ್ರಪದ',
    'Revati / ರೇವತಿ',
]

WORDS = {
    'satyanarayana':'ಸತ್ಯನಾರಾಯಣ', 'sathyanarayana':'ಸತ್ಯನಾರಾಯಣ',
    'satyanarayan':'ಸತ್ಯನಾರಾಯಣ', 'pooja':'ಪೂಜೆ', 'puja':'ಪೂಜೆ',
    'pooje':'ಪೂಜೆ', 'seva':'ಸೇವಾ', 'seve':'ಸೇವೆ', 'shri':'ಶ್ರೀ', 'sri':'ಶ್ರೀ',
    'nagabana':'ನಾಗಬನ', 'naagabana':'ನಾಗಬನ', 'yermal':'ಎರ್ಮಾಳ್', 'ermal':'ಎರ್ಮಾಳ್',
    'tambila':'ತಂಬಿಲ', 'thambila':'ತಂಬಿಲ', 'tanu':'ತನು', 'thanu':'ತನು',
    'annadana':'ಅನ್ನದಾನ', 'annadaana':'ಅನ್ನದಾನ', 'anna':'ಅನ್ನ',
    'prasada':'ಪ್ರಸಾದ', 'prasad':'ಪ್ರಸಾದ್', 'ganesha':'ಗಣೇಶ',
    'raviraj':'ರವಿರಾಜ್', 'shetty':'ಶೆಟ್ಟಿ', 'shashi':'ಶಶಿ',
    'rishabh':'ರಿಷಭ್', 'dubai':'ದುಬೈ', 'mangalore':'ಮಂಗಳೂರು',
    'bengaluru':'ಬೆಂಗಳೂರು', 'udupi':'ಉಡುಪಿ', 'uae':'ಯುಎಇ',
}
for label in RASHIS + NAKSHATRAS:
    roman, script = label.split(' / ')
    if ' ' not in roman:
        WORDS[roman.lower()] = script

# Long vowels use aa/ee/oo; T/D/N/L distinguish retroflex sounds.
VOWELS = {'aa':('ಆ','ಾ'), 'ii':('ಈ','ೀ'), 'ee':('ಈ','ೀ'),
          'uu':('ಊ','ೂ'), 'oo':('ಊ','ೂ'), 'ai':('ಐ','ೈ'),
          'au':('ಔ','ೌ'), 'a':('ಅ',''), 'i':('ಇ','ಿ'),
          'u':('ಉ','ು'), 'e':('ಎ','ೆ'), 'o':('ಒ','ೊ'),
          'A':('ಆ','ಾ'), 'I':('ಈ','ೀ'), 'U':('ಊ','ೂ'),
          'E':('ಏ','ೇ'), 'O':('ಓ','ೋ')}
CONSONANTS = {'ksh':'ಕ್ಷ', 'chh':'ಛ', 'kh':'ಖ', 'gh':'ಘ',
              'ch':'ಚ', 'Ch':'ಛ', 'jh':'ಝ', 'Th':'ಠ', 'Dh':'ಢ',
              'th':'ಥ', 'dh':'ಧ', 'ph':'ಫ', 'bh':'ಭ', 'sh':'ಶ',
              'Sh':'ಷ', 'ng':'ಙ', 'ny':'ಞ', 'k':'ಕ', 'g':'ಗ',
              'c':'ಕ', 'j':'ಜ', 'T':'ಟ', 'D':'ಡ', 'N':'ಣ',
              't':'ತ', 'd':'ದ', 'n':'ನ', 'p':'ಪ', 'b':'ಬ',
              'm':'ಮ', 'y':'ಯ', 'r':'ರ', 'l':'ಲ', 'L':'ಳ',
              'v':'ವ', 'w':'ವ', 's':'ಸ', 'h':'ಹ', 'f':'ಫ',
              'z':'ಝ', 'q':'ಕ', 'x':'ಕ್ಸ'}
TOKENS = sorted(set(VOWELS) | set(CONSONANTS), key=len, reverse=True)


def _word(word):
    if word.lower() in WORDS:
        return WORDS[word.lower()]
    # Ordinary Title Case is not an instruction to use a retroflex initial.
    if word.istitle() or word.isupper():
        word = word.lower()
    out=[]; pos=0; pending=False
    while pos < len(word):
        token=next((t for t in TOKENS if word.startswith(t,pos)),None)
        if not token:
            if pending:out.append('್');pending=False
            out.append(word[pos]);pos+=1;continue
        pos+=len(token)
        if token in VOWELS:
            out.append(VOWELS[token][1 if pending else 0]);pending=False
        else:
            if pending:out.append('್')
            out.append(CONSONANTS[token]);pending=True
    if pending:out.append('್')
    return ''.join(out)


def suggest(text):
    text=str(text)[:200]
    for label in RASHIS + NAKSHATRAS:
        roman, script=label.split(' / ')
        if text.strip().lower()==roman.lower():return script
    return re.sub(r'[A-Za-z]+',lambda match:_word(match.group()),text)


def normalize_label(text):
    return ' '.join(str(text).casefold().split())


# Category meanings, separate from phonetic spellings of people's names.
# Exact phrases only: do not compose unreviewed word-by-word translations.
LABELS = {
    'consumables':'ಬಳಕೆ ಸಾಮಗ್ರಿಗಳು',
    'pooja materials':'ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು', 'puja materials':'ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು',
    'flowers':'ಹೂವುಗಳು', 'flower':'ಹೂವು', 'fruits':'ಹಣ್ಣುಗಳು', 'fruit':'ಹಣ್ಣು',
    'flowers and fruits':'ಹೂವುಗಳು ಮತ್ತು ಹಣ್ಣುಗಳು',
    'flower decoration':'ಹೂವಿನ ಅಲಂಕಾರ', 'decoration':'ಅಲಂಕಾರ',
    'stage':'ವೇದಿಕೆ', 'stage setup':'ವೇದಿಕೆ ಸಿದ್ಧತೆ', 'stage setting':'ವೇದಿಕೆ ಸಿದ್ಧತೆ',
    'stage decoration':'ವೇದಿಕೆ ಅಲಂಕಾರ', 'sound system':'ಧ್ವನಿವ್ಯವಸ್ಥೆ',
    'lighting':'ಬೆಳಕಿನ ವ್ಯವಸ್ಥೆ', 'drinking water':'ಕುಡಿಯುವ ನೀರು',
    'water':'ನೀರು', 'milk':'ಹಾಲು', 'rice':'ಅಕ್ಕಿ', 'coconut':'ತೆಂಗಿನಕಾಯಿ',
    'coconuts':'ತೆಂಗಿನಕಾಯಿಗಳು', 'ghee':'ತುಪ್ಪ', 'oil':'ಎಣ್ಣೆ',
    'incense sticks':'ಅಗರಬತ್ತಿಗಳು', 'camphor':'ಕರ್ಪೂರ',
    'food':'ಆಹಾರ', 'food distribution':'ಅನ್ನದಾನ', 'annadana':'ಅನ್ನದಾನ',
    'annadana seva':'ಅನ್ನದಾನ ಸೇವೆ', 'anna prasada':'ಅನ್ನಪ್ರಸಾದ',
    'annaprasada':'ಅನ್ನಪ್ರಸಾದ', 'annaprasada seva':'ಅನ್ನಪ್ರಸಾದ ಸೇವೆ',
    'anna prasada seva':'ಅನ್ನಪ್ರಸಾದ ಸೇವೆ',
    'donation':'ದೇಣಿಗೆ', 'general donation':'ಸಾಮಾನ್ಯ ದೇಣಿಗೆ',
    'sponsorship':'ಪ್ರಾಯೋಜಕತ್ವ', 'voluntary contribution':'ಸ್ವಯಂಪ್ರೇರಿತ ದೇಣಿಗೆ',
    'transport':'ಸಾರಿಗೆ', 'transportation':'ಸಾರಿಗೆ', 'cleaning':'ಸ್ವಚ್ಛತೆ',
    'hall rent':'ಸಭಾಂಗಣದ ಬಾಡಿಗೆ', 'printing':'ಮುದ್ರಣ',
    'invitation':'ಆಮಂತ್ರಣ', 'invitations':'ಆಮಂತ್ರಣ ಪತ್ರಿಕೆಗಳು',
    'annual day':'ವಾರ್ಷಿಕೋತ್ಸವ', 'annual celebration':'ವಾರ್ಷಿಕೋತ್ಸವ',
    'satyanarayana pooja':'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ',
    'satyanarayana puja':'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ',
    'sri satyanarayana pooja':'ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ',
    'shri satyanarayana pooja':'ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ',
    'sri satyanarayana puja':'ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ',
    'satyanarayana pooja uae':'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ ಯುಎಇ',
    'sri satyanarayana pooja uae':'ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ ಯುಎಇ',
    'nagabana':'ನಾಗಬನ', 'yermal nagabana':'ಎರ್ಮಾಳ್ ನಾಗಬನ',
    'yermal nagabana annual day':'ಎರ್ಮಾಳ್ ನಾಗಬನ ವಾರ್ಷಿಕೋತ್ಸವ',
    'tanu':'ತನು', 'tanu seva':'ತನು ಸೇವೆ',
    'tambila':'ತಂಬಿಲ', 'tambila seva':'ತಂಬಿಲ ಸೇವೆ',
    'pooja':'ಪೂಜೆ', 'puja':'ಪೂಜೆ', 'seva':'ಸೇವೆ',
}


def translate_label(text, saved=None):
    key=normalize_label(text)
    if not key:return ''
    if saved and key in saved:return saved[key]
    if key in LABELS:return LABELS[key]
    # Kannada-only input is already usable; unknown English stays unanswered.
    if re.search(r'[\u0c80-\u0cff]',str(text)) and not re.search(r'[A-Za-z]',str(text)):
        return str(text)
    return ''


def bind_suggestion(source, target, converter=suggest):
    """Tk StringVars: update suggestions until the user edits the Kannada field.

    Existing nonempty saved text is treated as manual. Returns an explicit
    reset action; only that action may overwrite a manual correction.
    """
    state={'previous':None}
    def update(*_):
        current=target.get()
        if not current or current==state['previous']:
            value=converter(source.get());target.set(value);state['previous']=value
    def reset():
        value=converter(source.get());target.set(value);state['previous']=value
    source.trace_add('write',update)
    update()
    return reset


# Other common spellings (and English sign names) so typing finds the right entry.
ALIASES = {
    'Mesha / ಮೇಷ': 'mesh aries', 'Vrishabha / ವೃಷಭ': 'vrushabha rishabha vrushabh taurus',
    'Mithuna / ಮಿಥುನ': 'mithun gemini', 'Karkataka / ಕರ್ಕಾಟಕ': 'karka kataka karkata karkat cancer',
    'Simha / ಸಿಂಹ': 'simham singh leo', 'Kanya / ಕನ್ಯಾ': 'kanni virgo', 'Tula / ತುಲಾ': 'thula tulam libra',
    'Vrischika / ವೃಶ್ಚಿಕ': 'vrushchika vrishchika scorpio', 'Dhanu / ಧನು': 'dhanus dhanussu dhanur sagittarius',
    'Makara / ಮಕರ': 'makar capricorn', 'Kumbha / ಕುಂಭ': 'kumbh aquarius', 'Meena / ಮೀನ': 'mina meen pisces',
    'Ashwini / ಅಶ್ವಿನಿ': 'aswini asvini', 'Bharani / ಭರಣಿ': 'barani', 'Krittika / ಕೃತ್ತಿಕಾ': 'kruttika karthika kritika krithika',
    'Rohini / ರೋಹಿಣಿ': 'rohani', 'Mrigashira / ಮೃಗಶಿರ': 'mrigasira mrugashira mrigashirsha makayiram',
    'Ardra / ಆರ್ದ್ರ': 'arudra aridra thiruvathira', 'Punarvasu / ಪುನರ್ವಸು': 'punarpoosam', 'Pushya / ಪುಷ್ಯ': 'pushyami poosam pooyam',
    'Ashlesha / ಆಶ್ಲೇಷಾ': 'aslesha ashlesha ayilyam', 'Magha / ಮಘಾ': 'makha makam',
    'Purva Phalguni / ಪೂರ್ವ ಫಲ್ಗುಣಿ': 'pubba poorva pooram purvaphalguni',
    'Uttara Phalguni / ಉತ್ತರ ಫಲ್ಗುಣಿ': 'uttara uthra uthram uttaraphalguni', 'Hasta / ಹಸ್ತ': 'hastha atham',
    'Chitra / ಚಿತ್ರಾ': 'chitta chithira chittha', 'Swati / ಸ್ವಾತಿ': 'svati swathi chothi',
    'Vishakha / ವಿಶಾಖಾ': 'visakha vishaka vishakam', 'Anuradha / ಅನುರಾಧಾ': 'anusha anizham',
    'Jyeshtha / ಜ್ಯೇಷ್ಠಾ': 'jyeshta jyesta kettai triketta', 'Mula / ಮೂಲ': 'moola moolam',
    'Purva Ashadha / ಪೂರ್ವಾಷಾಢಾ': 'poorvashadha purvashada pooradam', 'Uttara Ashadha / ಉತ್ತರಾಷಾಢಾ': 'uttarashadha uthrashada uthradam',
    'Shravana / ಶ್ರವಣ': 'sravana shravan thiruvonam onam', 'Dhanishta / ಧನಿಷ್ಠಾ': 'dhanishtha shravishta avittam',
    'Shatabhisha / ಶತಭಿಷಾ': 'satabhisha shatataraka sadayam chathayam',
    'Purva Bhadrapada / ಪೂರ್ವಭಾದ್ರಪದ': 'poorvabhadra purvabhadra pooruruttathi',
    'Uttara Bhadrapada / ಉತ್ತರಭಾದ್ರಪದ': 'uttarabhadra uthrabhadra uthrattathi', 'Revati / ರೇವತಿ': 'revathi',
}


def rank_choices(query, choices, aliases=None):
    """Choices matching what was typed, best first: starts-with, then word/alias starts-with, then contains."""
    aliases = ALIASES if aliases is None else aliases
    q = ' '.join(str(query or '').casefold().split())
    if not q:
        return list(choices)
    scored = []
    for i, choice in enumerate(choices):
        text = choice.casefold()
        words = re.split(r'[\s/()]+', text) + aliases.get(choice, '').split()
        if text.startswith(q):
            score = 0
        elif any(w.startswith(q) for w in words if w):
            score = 1
        elif q in text or any(q in w for w in aliases.get(choice, '').split()):
            score = 2
        else:
            continue
        scored.append((score, i, choice))
    return [c for _, _, c in sorted(scored)]


def pick_choice(value, choices, label):
    """Accept an exact choice, blank, or a single clear match; otherwise explain."""
    value = str(value or '').strip()
    if not value or value in choices:
        return value
    ranked = rank_choices(value, choices)
    if ranked and (len(ranked) == 1 or rank_choices(value, choices)[0].casefold().startswith(value.casefold())):
        return ranked[0]
    raise ValueError(f'Choose {label} from the list (type a few letters, e.g. "{choices[0][:3].lower()}").')
