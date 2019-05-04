"""A module for parsing journal databases: NLM/PubMed and MathSciNet."""
from typing import Dict, Iterator, NamedTuple, Optional, Tuple
import re


class NLMJournal(NamedTuple):
    """Data from NLM/PubMed and NCBI database, see `parseNLM()`."""

    jrId: int
    # Matches `[0-9a-ZA-Z&'()+,./;="+<>$@?!\[\]\-]*`
    # `=` often used for translated titles, `"+<>$@?!` only in a few.
    journalTitle: str
    # Mostly dotless, matches `[ 0-9A-Za-z&'(),.:/\-\[\]]+`
    medAbbr: Optional[str]
    # Almost always dotted, matches same, not really standard ISO-4.
    isoAbbr: Optional[str]
    # Matches `[0-9]{4}-[0-9]{3}[0-9xX]`
    issnOnline: Optional[str]
    # Matches same.
    issnPrint: Optional[str]
    # Matches `[0-9]+(A|R|)`
    nlmId: str


def parseNLM(filename: str) -> Iterator[NLMJournal]:
    """Parse journal data from NLM/PubMed and NCBI database.

    Returns dict from ISSN (both online and print) to NLMJournal.

    The file is 'J_Entrez.txt' (which contains the other two) at:
    https://www.ncbi.nlm.nih.gov/books/NBK3827/table/pubmedhelp.T.journal_lists/
    ftp://ftp.ncbi.nih.gov/pubmed/J_Entrez.txt
    """
    journal: Dict[str, str] = {}
    with open(filename, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            if line.strip() != ('-' * 56):
                k, v = line.split(':', 1)
                journal[k.strip()] = v.strip()
                continue
            if not journal:
                continue
            nlmJournal = NLMJournal(
                jrId=int(journal['JrId']),
                journalTitle=journal['JournalTitle'],
                medAbbr=journal['MedAbbr'] or None,
                isoAbbr=journal['IsoAbbr'] or None,
                issnOnline=journal['ISSN (Online)'] or None,
                issnPrint=journal['ISSN (Print)'] or None,
                nlmId=journal['NlmId']
            )
            abbrevRegex = r'[ 0-9A-Za-z&\'(),.:/\-\[\]]+'
            if nlmJournal.medAbbr:
                assert re.fullmatch(abbrevRegex, nlmJournal.medAbbr)
            if nlmJournal.isoAbbr:
                assert re.fullmatch(abbrevRegex, nlmJournal.isoAbbr)
            issnRegex = r'[0-9]{4}-[0-9]{3}[0-9xX]'
            if nlmJournal.issnOnline:
                assert re.fullmatch(issnRegex, nlmJournal.issnOnline)
            if nlmJournal.issnPrint:
                assert re.fullmatch(issnRegex, nlmJournal.issnPrint)
            assert re.fullmatch(r'[0-9]+(A|R|)', nlmJournal.nlmId)
            journal = {}
            yield nlmJournal


def parseNLMDict() -> Dict[str, str]:
    """Parse NLM/PubMed data as dict from ISSN to abbrev."""
    result: Dict[str, str] = {}
    for j in parseNLM('databaseNLM.txt'):
        if j.medAbbr:
            if j.issnOnline:
                result[j.issnOnline] = j.medAbbr
            if j.issnPrint:
                result[j.issnPrint] = j.medAbbr
    return result


class MSNJournal(NamedTuple):
    """Data from MathSciNet database, see `parseMSN()`."""

    year: int
    issn: Optional[str]  # Matches `[0-9]{4}-[0-9]{3}[0-9xX]`
    abbrev: str  # Dotted, matches `[ 0-9A-Za-z()\-./]+`
    publisher: str


def parseMSN(filename: str) -> Iterator[MSNJournal]:
    """Parse journal data from MathSciNet database.

    The file is available at:
    https://mathscinet.ams.org/mathscinet/search/newj.html
    https://mathscinet.ams.org/mathscinet/search/newjCSV.html
    """
    import csv
    with open(filename, 'r', newline='\n') as f:
        reader = csv.reader(f, dialect='excel')
        for row in reader:
            if not row or row[0] == 'Year':
                continue
            assert len(row) == 5
            msnJournal = MSNJournal(
                year=int(row[0]),
                issn=row[1] or None,
                abbrev=row[2].strip(),
                publisher=row[3].strip(),
            )
            issnRegex = r'[0-9]{4}-[0-9]{3}[0-9xX]'
            if msnJournal.issn:
                assert re.fullmatch(issnRegex, msnJournal.issn)
            assert re.fullmatch(r'[ 0-9A-Za-z()\-./]+', msnJournal.abbrev)
            url = ('https://mathscinet.ams.org/mathscinet/'
                   'search/journaldoc.html?cn=')
            assert row[4].startswith(url)
            assert row[4][len(url):] == row[1].replace('-', '')
            yield msnJournal


def parseMSNDict() -> Dict[str, str]:
    """Parse MathSciNet data as dict from ISSN to abbrev."""
    result: Dict[str, str] = parseMSN2('databaseMathSciNet.html')
    for j in parseMSN('databaseMathSciNet.csv'):
        if j.issn:
            # Overwrite with csv version, as it has less errors.
            result[j.issn] = j.abbrev
    return result


def parseMSN2(filename: str) -> Dict[str, str]:
    """Parse journal data from MathSciNet database.Less reliable.

    This version tries parsing the pdf obtained as below.
    This gives a few mistakes, but this list is more complete (2411 vs 884).
    Both versions have many ISSNs not in the other, but it seems the smaller
    one has different ISSNs of the same journals.
    pdftohtml -i -s -c serials.pdf
    https://mathscinet.ams.org/msnhtml/serials.pdf
    """
    from unicodedata import normalize
    result: Dict[str, str] = {}
    with open(filename) as f:
        # Parse font description lines.
        fonts: Dict[int, Tuple[int, int, int]] = {}
        ii = 0
        for line in f:
            if 'p {margin: 0' in line:
                ii = 0
            m = re.search(r'\.ft([0-9]+)\{font-size:([0-9]+)px', line)
            if m:
                ii += 1
                fontId = int(m.group(1))
                fontSize = int(m.group(2))
                m2 = re.search(r'line-height:([0-9]+)px', line)
                lineHeight = int(m2.group(1)) if m2 else 0
                fonts[fontId] = (ii, fontSize, lineHeight)
        # Parse text content lines.
        f.seek(0)
        fulltext = '\n'.join(f.readlines())
        fulltext = fulltext.replace('<br/>', '&lt;br/&gt;')
        fulltext += '<p style="top:-1000px;left:0px;" class="ft0"></p>'
        matches = re.finditer(r'<p style="'
                              r'[a-z:\-;]*top:([0-9]+)px'
                              r'[a-z:\-;]*left:([0-9]+)px'
                              r'[a-z:\-;]*'
                              r'" class="ft([0-9]+)">([^<]*)</p>',
                              fulltext,
                              re.M)
        prevTop = -100
        prevLeft = 100000
        prevLen = 0
        prevFont = (0, 0, 0)
        curAbbrev = ''
        curText = ''
        curISSN = ''
        for m in matches:
            top = int(m.group(1))
            left = int(m.group(2))
            fontId = int(m.group(3))
            text = m.group(4)
            text = text.replace(' ', '')
            text = text.replace('&#160;', ' ')
            font = fonts.get(fontId, (0, 0, 0))
            newItem = False
            newPage = top < prevTop - 1000
            movedLeft = left < prevLeft - 5
            movedDown = top > prevTop + 9
            if newPage or movedLeft or movedDown or prevLen > 3:
                if left <= 170 or (left > 760 and left <= 784):
                    newItem = True
            if newItem:
                abbrev = normalize('NFKC', curAbbrev).strip()
                abbrev = abbrev.replace(' ́e', 'é')
                abbrev = abbrev.replace(' ́E', 'É')
                abbrev = abbrev.replace(' ̈u', 'ü')
                abbrev = abbrev.replace(' ̈o', 'ö')
                abbrev = abbrev.replace(' ̃a', 'ã')
                abbrev = abbrev.replace('ˇS', 'Š')
                abbrev = abbrev.replace('`E', 'È')
                abbrev = abbrev.replace(' ̄a', 'ā')
                abbrev = abbrev.replace(' ̄ı', 'ī')
                abbrev = abbrev.replace(' ̆ı', 'ǐ')
                abbrev = abbrev.replace(' ́ı', 'í')
                abbrev = abbrev.replace(' ́o', 'ó')
                abbrev = abbrev.replace(' ́z', 'ź')
                issnm = re.search(r'[0-9]{4}-[0-9]{3}[0-9X]', curISSN)
                if issnm:
                    issn = issnm.group(0)
                    result[issn] = abbrev
                curAbbrev = ''
                curText = ''
                curISSN = ''
            if text not in ['∗', '†', '§', '∗§'] and font[1] < 15:
                if len(text) in [1, 2] and re.match(r'[(A-Z]', text):
                    curText += ' ' + text
                elif text.startswith('Col') and curText.endswith('o'):
                    curText += ' ' + text
                else:
                    curText += text
                if font[1] == 12:
                    curAbbrev = curText
                elif prevFont[1] == 12 and len(text) < 4 \
                        and not curText.startswith(text) \
                        and not re.match('[A-Z]', text):
                    curAbbrev = curText
                else:
                    if 'ISSN' in curText:
                        curISSN += text
                # print(f'{top}x{left} ft={font} "{text}"')
            prevTop = top
            prevLeft = left
            prevLen = len(text)
            prevFont = font
    return result
