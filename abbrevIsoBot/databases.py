"""A module for parsing journal databases: NLM/PubMed and MathSciNet."""
from typing import Dict, Iterator, NamedTuple, Optional
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


def parseNLMDict(filename: str) -> Dict[str, str]:
    """Parse NLM/PubMed data as dict from ISSN to abbrev."""
    result: Dict[str, str] = {}
    for j in parseNLM(filename):
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


def parseMSNDict(filename: str) -> Dict[str, str]:
    """Parse MathSciNet data as dict from ISSN to abbrev."""
    result: Dict[str, str] = {}
    for j in parseMSN(filename):
        if j.issn:
            result[j.issn] = j.abbrev
    return result
