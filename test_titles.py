import habanero
import bibtexparser
# from fuzzywuzzy import fuzz
from difflib import ndiff

with open('Exported Items.bib') as bibtex_file:
    bibtex_database = bibtexparser.load(bibtex_file)

for b in bibtex_database.entries:
    if 'doi' in b:
        ref = habanero.Crossref().works(ids=b['doi'])['message']['title'][0]
        if not ref.endswith('\n'):
            ref += '\n'
        title = b['title'].replace('{', '').replace('}', '') + '\n'
        if not title.endswith('\n'):
            title += '\n'
        if all([a.startswith(' ') for a in ndiff([ref], [title])]):
            continue
        else:
            print(''.join(ndiff([ref], [title])))
        # break
