#!/usr/bin/env python3
"""Batch converter: ReSpecTh v2.3/v2.4 XML → ChemKED YAML

Converts experiment XML files from ReSpecTh/indirect/ to ChemKED YAML format
and organises them into ChemKED-database directory structure.

Usage:
    python batch_convert.py
    python batch_convert.py -i ReSpecTh/indirect -o ChemKED-database
    python batch_convert.py --file ReSpecTh/indirect/ammonia/.../x20100057.xml
    python batch_convert.py --dry-run
"""

import importlib
import os
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import yaml
import argparse
import logging

try:
    from pyked.chemked import ChemKED as _ChemKED
except Exception:
    _ChemKED = None

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)


def _get_chemked_version():
    """Return the ChemKED schema version from the packaged schema, or a default."""
    default = '0.4.1'
    try:
        schema_mod = importlib.import_module('pyked.validation')
    except ImportError:
        return default
    schema = getattr(schema_mod, 'schema', None)
    if not isinstance(schema, dict):
        return default
    allowed = schema.get('chemked-version', {}).get('allowed')
    if isinstance(allowed, (list, tuple)) and allowed:
        return str(allowed[-1])
    return default


CHEMKED_VERSION = _get_chemked_version()


class UnsupportedUnitsError(Exception):
    """Raised when composition uses units not supported by the ChemKED schema."""


# Custom YAML dumper that preserves dict insertion order and indents block sequences
class _OrderedDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow=flow, indentless=False)

def _dict_representer(dumper, data):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                   data.items())

_OrderedDumper.add_representer(dict, _dict_representer)


class _FlowList(list):
    """List subclass that signals the YAML dumper to use flow style."""
    pass

def _flow_list_representer(dumper, data):
    return dumper.represent_sequence(yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, data, flow_style=True)

_OrderedDumper.add_representer(_FlowList, _flow_list_representer)


def yaml_dump(data, stream):
    """Dump data to YAML preserving dict key order with indented block sequences."""
    stream.write('---\n')
    yaml.dump(data, stream, Dumper=_OrderedDumper,
              default_flow_style=False, allow_unicode=True)
    stream.write('...\n')

# Experiment type mapping (ReSpecTh text → ChemKED value)
EXP_TYPE_MAP = {
    'ignition delay measurement': 'ignition delay',
    'laminar burning velocity measurement': 'laminar burning velocity measurement',
    'concentration time profile measurement': 'concentration time profile measurement',
    'jet stirred reactor measurement': 'jet stirred reactor measurement',
    'outlet concentration measurement': 'outlet concentration measurement',
    'burner stabilized flame speciation measurement': 'burner stabilized flame speciation measurement',
}

# Properties valid as scalar value+unit in dataGroups
SCALAR_DG_PROPS = {
    'temperature', 'pressure', 'ignition delay', 'pressure rise',
    'laminar burning velocity', 'distance', 'flow rate',
    'residence time', 'volumetric flow rate in reference state',
    'volume', 'time', 'environment temperature',
    'rate coefficient', 'branching ratio',
}

# Properties valid as scalar value+unit in commonProperties
SCALAR_COMMON_PROPS = {
    'temperature', 'pressure', 'residence time', 'volume',
    'flow rate', 'reactor volume', 'pressure rise',
    'laminar burning velocity', 'environment temperature',
    'global heat exchange coefficient', 'exchange area',
    'reactor length', 'reactor diameter',
    'pressure in reference state', 'temperature in reference state',
}


# Compact inverse-unit notation used in ReSpecTh that pint cannot parse.
# e.g. "ms-1" is ambiguous (pint reads it as millisecond, dimensionless);
# map to unambiguous reciprocal forms. Mirrors converters.py's "Torr"→"torr".
_INV_UNIT_MAP = {'ms-1': '1/ms', 's-1': '1/s', 'cm-1': '1/cm', 'K-1': '1/K',
                 'unitless': 'dimensionless'}


def _normalize_units(unit_str):
    """Rewrite unit strings with implicit negative exponents to pint-compatible form.

    Converts e.g. 'kg m-2 s-1' → 'kg * m**-2 * s**-1' so that pint does not
    misinterpret the '-' as arithmetic subtraction.
    Also handles ReSpecTh underscore-separated units like 'cm3_mol-1_s-1'.
    """
    import re as _re
    # First apply the simple inverse map
    unit_str = _INV_UNIT_MAP.get(unit_str, unit_str)
    # Replace underscore separators with spaces (ReSpecTh k-file convention: cm3_mol-1_s-1)
    # Only replace underscores that appear between unit token characters (not leading/trailing)
    unit_str = _re.sub(r'(?<=\w)_(?=\w)', ' ', unit_str)
    # Replace patterns like 'TOKEN-N' (letter/digit token followed by hyphen-digit)
    # with 'TOKEN**-N', but only when the token is a known unit symbol (not a standalone '-').
    unit_str = _re.sub(r'([a-zA-Z]+)(-\d+)', r'\1**\2', unit_str)
    # Replace spaces used as implicit multiplication with ' * '
    # (only between unit tokens, not touching '**')
    unit_str = _re.sub(r'(?<=\w) +(?=\w)', ' * ', unit_str)
    return unit_str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decode_latex(s):
    """Decode LaTeX accent commands to Unicode characters.

    Handles patterns like {\\'{e}} → é, {\\"\\{u}} → ü, {\\`{e}} → è, etc.
    Also strips remaining braces from BibTeX-style {name} groups.
    """
    import re
    # Mapping of (accent_command, base_letter) → Unicode character
    _accent_map = {
        ("'", 'a'): 'á', ("'", 'A'): 'Á',
        ("'", 'e'): 'é', ("'", 'E'): 'É',
        ("'", 'i'): 'í', ("'", 'I'): 'Í',
        ("'", 'o'): 'ó', ("'", 'O'): 'Ó',
        ("'", 'u'): 'ú', ("'", 'U'): 'Ú',
        ('"', 'a'): 'ä', ('"', 'A'): 'Ä',
        ('"', 'e'): 'ë', ('"', 'E'): 'Ë',
        ('"', 'i'): 'ï', ('"', 'I'): 'Ï',
        ('"', 'o'): 'ö', ('"', 'O'): 'Ö',
        ('"', 'u'): 'ü', ('"', 'U'): 'Ü',
        ('`', 'a'): 'à', ('`', 'A'): 'À',
        ('`', 'e'): 'è', ('`', 'E'): 'È',
        ('`', 'i'): 'ì', ('`', 'I'): 'Ì',
        ('`', 'o'): 'ò', ('`', 'O'): 'Ò',
        ('`', 'u'): 'ù', ('`', 'U'): 'Ù',
        ('^', 'a'): 'â', ('^', 'A'): 'Â',
        ('^', 'e'): 'ê', ('^', 'E'): 'Ê',
        ('^', 'i'): 'î', ('^', 'I'): 'Î',
        ('^', 'o'): 'ô', ('^', 'O'): 'Ô',
        ('^', 'u'): 'û', ('^', 'U'): 'Û',
        ('~', 'n'): 'ñ', ('~', 'N'): 'Ñ',
        ('c', 'c'): 'ç', ('c', 'C'): 'Ç',
    }

    def _replace_accent(m):
        accent = m.group(1)
        letter = m.group(2)
        return _accent_map.get((accent, letter), letter)

    # Pattern: {\CMD{letter}} or {\\CMD{letter}} where CMD is one of ' " ` ^ ~ c
    # Outer braces may or may not be present
    s = re.sub(r"\{?\\(['\"`^~c])\{([A-Za-z])\}\}?", _replace_accent, s)
    # Also handle \\' without inner braces: {\'A} or \'{A}
    s = re.sub(r"\{?\\(['\"`^~c])([A-Za-z])\}?", _replace_accent, s)
    # Handle LaTeX \# → # and \& → &
    s = s.replace('\\#', '#').replace('\\&', '&')
    # Handle \text{...} → contents
    s = re.sub(r'\\text\{([^}]*)\}', r'\1', s)
    # Handle \textquotesingle → '
    s = s.replace('\\textquotesingle', "'")
    # Strip remaining BibTeX braces {word} → word
    s = re.sub(r'\{([^{}]*)\}', r'\1', s)
    # Clean up any double spaces
    s = re.sub(r'  +', ' ', s).strip()
    return s


def parse_author_string(s):
    """Parse author strings into [{'name': 'First Last'}, ...].

    Handles two common ReSpecTh formats:
    - 'Last, First and Last, First ...'  (and-separated)
    - 'Last, F., Last, F., ...'          (comma-separated initials, no 'and')
    """
    import re as _re
    s = s.strip()
    authors = []

    # Detect comma-only format: 'Last, F., Last, F., ...'
    # Heuristic: if ' and ' is absent but the string has repeated 'Word, X.,' pattern
    if ' and ' not in s and _re.search(r'\w+,\s+\w+\.(?:,|$)', s):
        # Split on ', ' followed by a word that is itself followed by ', ' or end
        # Strategy: collect tokens by splitting on ', ' and pairing them up
        tokens = [t.strip() for t in s.split(',')]
        tokens = [t for t in tokens if t]
        i = 0
        while i < len(tokens):
            last = tokens[i]
            # Next token is the initial/first name (may end with '.')
            if i + 1 < len(tokens):
                first = tokens[i + 1].strip()
                name = f"{first} {last}"
                i += 2
            else:
                name = last
                i += 1
            authors.append({'name': decode_latex(name)})
        return authors

    # Standard 'and'-separated format
    for part in s.split(' and '):
        part = part.strip()
        if not part:
            continue
        if ',' in part:
            pieces = part.split(',', 1)
            name = f"{pieces[1].strip()} {pieces[0].strip()}"
        else:
            name = part
        authors.append({'name': decode_latex(name)})
    return authors


def first_author_last_name(authors):
    """Return first author's last name for directory naming."""
    if not authors:
        return 'Unknown'
    name = authors[0].get('name', 'Unknown')
    parts = name.strip().split()
    return parts[-1] if parts else 'Unknown'


def parse_species_link(elem):
    """Extract species info dict from a <speciesLink> element."""
    info = {}
    pk = elem.attrib.get('preferredKey', '')
    if pk:
        info['species-name'] = pk
    inchi = elem.attrib.get('InChI')
    if inchi:
        info['InChI'] = inchi
    return info


def _clean_numeric(text):
    """Clean numeric string: strip leading zeros to avoid YAML octal issues."""
    import re as _re
    text = text.strip()
    # Handle Fortran-style exponents without 'e': e.g. '5.93+005' → '5.93e+005'
    text = _re.sub(r'^([+-]?\d+\.?\d*)([+-]\d+)$', r'\1e\2', text)
    try:
        val = float(text)
        if val != val:  # NaN
            return text
        # Integer-valued: format as integer string
        if val == int(val) and '.' not in text and 'e' not in text.lower():
            return str(int(val))
        # Otherwise format cleanly (strips trailing zeros, avoids float noise)
        return f'{val:.15g}'
    except (ValueError, OverflowError):
        return text


def normalize_comp_units(value_str, units):
    """Normalise composition amount → (float, kind_string).

    Matches the existing PyKED converter convention:
      - percent  → mole percent  (value unchanged)
      - ppm      → mole fraction (value × 1e-6)
      - ppb      → mole fraction (value × 1e-9)
      - mole fraction / mass fraction / mole percent → unchanged
    """
    val = float(value_str)
    if units in ('mole fraction', 'mass fraction', 'mole percent'):
        return val, units
    elif units in ('percent',):
        return val, 'mole percent'
    elif units == 'ppm':
        return float(f'{val * 1e-6:.12g}'), 'mole fraction'
    elif units == 'ppb':
        return float(f'{val * 1e-9:.12g}'), 'mole fraction'
    elif units in ('mol/cm3', 'mol/m3', 'mol/L', 'mol/dm3'):
        return val, units
    else:
        raise UnsupportedUnitsError(
            f'Composition units {units!r} not supported. '
            'Must be one of: mole fraction, mass fraction, mole percent, '
            'percent, ppm, ppb, or mol/cm3.'
        )


def _reconcile_composition(entries):
    """Pick a single kind for the composition block.

    *entries*: list of (spec_dict, value, kind) tuples.
    Returns (target_kind, [(spec_dict, value)]).
    After normalisation, all entries should share the same kind.
    If mixed, the dominant kind is used and minority entries are converted.
    """
    kinds = set(e[2] for e in entries)
    if len(kinds) == 1:
        k = kinds.pop()
        return k, [(e[0], e[1]) for e in entries]
    # Mixed units – pick dominant kind, convert minority entries
    kind_counts = Counter(e[2] for e in entries)
    dominant = kind_counts.most_common(1)[0][0]
    log.warning(f'Mixed composition units {dict(kind_counts)}; converting all to {dominant!r}')
    converted = []
    for spec, val, kind in entries:
        if kind == dominant:
            converted.append((spec, val))
        elif dominant == 'mole fraction' and kind == 'mole percent':
            converted.append((spec, round(val / 100.0, 12)))
        elif dominant == 'mole percent' and kind == 'mole fraction':
            converted.append((spec, round(val * 100.0, 12)))
        else:
            # Fallback: convert both to mole fraction via ppm/ppb already handled upstream
            converted.append((spec, val))
    return dominant, converted


def prop_name_to_key(name):
    """Convert ReSpecTh property name to ChemKED YAML key."""
    key = name.replace(' ', '-')
    special = {
        'volume': 'reactor-volume',
        'volumetric-flow-rate-in-reference-state': 'volumetric-flow-in-reference-state',
        'environment-temperature': 'environment-temperature',
        'global-heat-exchange-coefficient': 'global-heat-exchange-coefficient',
        'exchange-area': 'exchange-area',
        'reactor-length': 'reactor-length',
        'reactor-diameter': 'reactor-diameter',
        'pressure-in-reference-state': 'pressure-in-reference-state',
        'temperature-in-reference-state': 'temperature-in-reference-state',
    }
    return special.get(key, key)


# ---------------------------------------------------------------------------
# File metadata & reference
# ---------------------------------------------------------------------------

def parse_file_metadata(root):
    file_author = (root.findtext('fileAuthor') or '').strip()
    props = {
        'file-authors': [{'name': file_author or 'Unknown'}],
        'file-version': 0,
        'chemked-version': CHEMKED_VERSION,
    }

    # Note: file-doi, respecth-version, first-publication-date, last-modification-date
    # are ReSpecTh-specific fields not recognised by the PyKED schema — omit them.

    return props


def parse_reference(root, xml_filename):
    import re as _re
    ref = {}
    bib = root.find('bibliographyLink')
    if bib is None:
        ref['detail'] = f'Converted from ReSpecTh XML file {xml_filename}'
        return ref

    doi_el = bib.find('referenceDOI')
    if doi_el is not None and doi_el.text:
        ref['doi'] = doi_el.text.strip()

    details = bib.find('details')
    if details is not None:
        auth = (details.findtext('author') or '').strip()
        if auth:
            ref['authors'] = parse_author_string(auth)
        journal = (details.findtext('journal') or '').strip()
        if journal:
            ref['journal'] = decode_latex(journal)
        year = (details.findtext('year') or '').strip()
        if year:
            ref['year'] = int(year)
        vol = (details.findtext('volume') or '').strip()
        if vol:
            try:
                # handles '32 I' → 32, '110–111' or '110-111' → 110
                m_vol = _re.search(r'\d+', vol)
                ref['volume'] = int(m_vol.group()) if m_vol else int(vol.split()[0])
            except (ValueError, IndexError, AttributeError):
                pass  # omit non-parseable volume; CrossRef enrichment will set it
        pages = (details.findtext('pages') or '').strip()
        if pages:
            # Normalise en-dash/double-hyphen page ranges to single hyphen (e.g. 239--245 → 239-245)
            pages = _re.sub(r'-{2,}', '-', pages).replace('\u2013', '-')
            ref['pages'] = pages
        # Note: title, location, table, figure, number, publication-type are not
        # recognised by the PyKED schema — omit them.

    # Fallback: use <description>
    if not ref.get('authors'):
        desc = (bib.findtext('description') or '').strip()
        if desc:
            ref['detail'] = desc

    prefix = ref.get('detail', '')
    ref['detail'] = (prefix + ' ' if prefix else '') + \
                    f'Converted from ReSpecTh XML file {xml_filename}'

    # Enrich journal name and authors from CrossRef so the YAML matches
    # what PyKED's CrossRef validation expects.
    if ref.get('doi'):
        try:
            import habanero as _habanero
            from requests.exceptions import ConnectionError as _ConnErr
            _cr = _habanero.Crossref(mailto='prometheus@pr.omethe.us')
            _msg = _cr.works(ids=ref['doi'])['message']
            # Canonical journal title
            container = _msg.get('container-title')
            if container:
                import html as _html_mod
                ref['journal'] = _html_mod.unescape(container[0])
            # Canonical author list: family + given → "Given Family"
            cr_authors = _msg.get('author', [])
            if cr_authors:
                names = []
                for a in cr_authors:
                    given = a.get('given', '').strip()
                    family = a.get('family', '').strip()
                    if given and family:
                        names.append({'name': f'{given} {family}'})
                    elif family:
                        names.append({'name': family})
                if names:
                    ref['authors'] = names
            # Canonical year
            pub = _msg.get('published-print') or _msg.get('published-online') or _msg.get('published') or _msg.get('issued')
            if pub:
                ref['year'] = pub['date-parts'][0][0]
            # Canonical volume (integer)
            cr_vol = _msg.get('volume')
            if cr_vol is not None:
                try:
                    # CrossRef may return combined volumes like "110-111"; use first number
                    m_cv = _re.search(r'\d+', str(cr_vol))
                    ref['volume'] = int(m_cv.group()) if m_cv else int(cr_vol)
                except (ValueError, TypeError, AttributeError):
                    pass
            # Canonical pages (some journals use article-number instead of page)
            cr_pages = _msg.get('page') or _msg.get('article-number')
            if cr_pages:
                ref['pages'] = _re.sub(r'-{2,}', '-', cr_pages).replace('\u2013', '-')
        except Exception:
            pass  # network unavailable or DOI not in CrossRef — keep ReSpecTh values

    return ref


# ---------------------------------------------------------------------------
# Experiment kind & apparatus
# ---------------------------------------------------------------------------

def parse_experiment_kind(root):
    exp_text = (root.findtext('experimentType') or '').strip().lower()
    exp_type = EXP_TYPE_MAP.get(exp_text)
    if exp_type is None:
        raise ValueError(f'Unknown experiment type: {root.findtext("experimentType")}')

    _default_apparatus_kind = {
        'ignition delay': 'shock tube',
        'laminar burning velocity measurement': 'outwardly propagating spherical flame',
        'concentration time profile measurement': 'flow reactor',
        'jet stirred reactor measurement': 'jet stirred reactor',
        'outlet concentration measurement': 'flow reactor',
        'burner stabilized flame speciation measurement': 'flame',
    }
    apparatus = {'kind': '', 'institution': '', 'facility': ''}
    kind_el = root.find('apparatus/kind')
    if kind_el is not None and kind_el.text:
        apparatus['kind'] = kind_el.text.strip()
    if not apparatus['kind'] and exp_type in _default_apparatus_kind:
        apparatus['kind'] = _default_apparatus_kind[exp_type]
    _mode_aliases = {
        'reflected': 'reflected shock',
        'incident': 'incident shock',
    }
    modes = root.findall('apparatus/mode')
    if modes:
        mode_list = []
        for m in modes:
            if m.text:
                raw = m.text.strip()
                mode_list.append(_mode_aliases.get(raw, raw))
        if mode_list:
            apparatus['mode'] = mode_list

    return exp_type, apparatus


# ---------------------------------------------------------------------------
# Common properties
# ---------------------------------------------------------------------------

def parse_initial_composition(prop_elem):
    entries = []  # [(spec_dict, value, kind)]
    for component in prop_elem.findall('component'):
        sl = component.find('speciesLink')
        amount_el = component.find('amount')
        if sl is None or amount_el is None:
            continue
        spec = parse_species_link(sl)
        units = amount_el.attrib.get('units', 'mole fraction')
        val, kind = normalize_comp_units(amount_el.text, units)
        entries.append((spec, val, kind))
    comp = {'kind': None, 'species': []}
    if not entries:
        return comp
    target_kind, resolved = _reconcile_composition(entries)
    comp['kind'] = target_kind
    for spec, val in resolved:
        spec['amount'] = [val]
        comp['species'].append(spec)
    return comp


def _ref_to_property_key(reference, dg_defs=None):
    """Map a ReSpecTh uncertainty reference string to a ChemKED property key.

    Returns None for composition/initial-composition references (per-species,
    no scalar property to attach to).
    """
    if reference in ('composition', 'initial composition'):
        return None
    alias_map = {
        'Sl': 'laminar-burning-velocity',
        'SL': 'laminar-burning-velocity',
        'Phi': 'equivalence-ratio',
    }
    if reference in alias_map:
        return alias_map[reference]
    # If reference looks like a dataGroup column id (e.g. 'x1'), resolve it
    if dg_defs and reference in dg_defs:
        return prop_name_to_key(dg_defs[reference]['name'])
    # General case: space→hyphen
    return prop_name_to_key(reference)


def _format_unc_value(value_str, units, kind='absolute'):
    """Format an uncertainty value, stripping dimensionless ``[-]`` notation."""
    if units in ('[-]', '', 'unitless'):
        return value_str
    if kind == 'relative':
        return value_str
    return f'{value_str} {units}'.strip()


def _bound_key(bound):
    """Map a ReSpecTh bound attribute to the PyKED uncertainty key name."""
    if bound == 'plus':
        return 'upper-uncertainty'
    elif bound == 'minus':
        return 'lower-uncertainty'
    return 'uncertainty'


def _build_inline_uncertainty(kind, bound, value_str, units, sourcetype=None):
    """Build a PyKED inline uncertainty dict from ReSpecTh attributes."""
    unc_dict = {'uncertainty-type': kind}
    unc_value = _format_unc_value(value_str, units, kind)
    unc_dict[_bound_key(bound)] = unc_value
    if sourcetype:
        unc_dict['uncertainty-sourcetype'] = sourcetype
    return unc_dict


def _merge_inline_uncertainty(existing, new):
    """Merge two inline uncertainty dicts (e.g. separate plus + minus → one dict)."""
    merged = dict(existing)
    for key in ('uncertainty-type', 'uncertainty', 'upper-uncertainty', 'lower-uncertainty',
                'uncertainty-sourcetype'):
        if key in new:
            merged[key] = new[key]
    return merged


def _build_inline_esd(kind, value_str, units, sourcetype=None, method=None):
    """Build inline evaluated-standard-deviation fields for a property dict."""
    esd = {}
    esd['evaluated-standard-deviation'] = _format_unc_value(value_str, units, kind)
    if kind:
        esd['evaluated-standard-deviation-type'] = kind
    if sourcetype:
        esd['evaluated-standard-deviation-sourcetype'] = sourcetype
    if method:
        esd['evaluated-standard-deviation-method'] = method
    return esd


def _attach_metadata_to_property(dp, key, fields):
    """Merge metadata fields into a property's inline dict on dp[key]."""
    prop_val = dp.get(key)
    if not isinstance(prop_val, list) or len(prop_val) < 1:
        return False
    if len(prop_val) >= 2 and isinstance(prop_val[1], dict):
        prop_val[1].update(fields)
    else:
        dp[key] = [prop_val[0], dict(fields)]
    return True


def _attach_comp_esd_inline(comp_block, species_name, kind, raw_value, units,
                            sourcetype=None, method=None):
    """Attach inline ESD fields to a species amount dict in a composition block."""
    for spec in comp_block.get('species', []):
        if spec.get('species-name') != species_name:
            continue
        amount = spec.get('amount')
        if not isinstance(amount, list) or len(amount) < 1:
            return False
        if units in ('ppm', 'ppb', 'percent'):
            esd_val, _ = normalize_comp_units(str(raw_value), units)
        else:
            esd_val = float(raw_value)
        esd_fields = {'evaluated-standard-deviation': esd_val}
        if kind:
            esd_fields['evaluated-standard-deviation-type'] = kind
        if sourcetype:
            esd_fields['evaluated-standard-deviation-sourcetype'] = sourcetype
        if method:
            esd_fields['evaluated-standard-deviation-method'] = method
        if len(amount) >= 2 and isinstance(amount[1], dict):
            amount[1].update(esd_fields)
        else:
            spec['amount'] = [amount[0], esd_fields]
        return True
    return False


def _attach_comp_uncertainty_inline(comp_block, species_name, kind, bound,
                                    raw_value, units, sourcetype=None):
    """Attach inline uncertainty to a species amount in a composition block.

    Composition amounts use bare floats, so uncertainty values are also floats
    (in the same implicit units as the composition ``kind``).

    Returns True if successfully attached, False if species not found.
    """
    for spec in comp_block.get('species', []):
        if spec.get('species-name') != species_name:
            continue
        amount = spec.get('amount')
        if not (isinstance(amount, list) and len(amount) >= 1):
            return False

        # Compute float uncertainty value
        if kind == 'relative':
            unc_val = float(raw_value)
        else:  # absolute
            if units in ('ppm', 'ppb', 'percent'):
                unc_val, _ = normalize_comp_units(str(raw_value), units)
            else:
                unc_val = float(raw_value)

        unc_dict = {'uncertainty-type': kind}
        if bound in ('plusminus', ''):
            unc_dict['uncertainty'] = unc_val
        elif bound == 'plus':
            unc_dict['upper-uncertainty'] = unc_val
        elif bound == 'minus':
            unc_dict['lower-uncertainty'] = unc_val
        else:
            unc_dict['uncertainty'] = unc_val
        if sourcetype:
            unc_dict['uncertainty-sourcetype'] = sourcetype

        if len(amount) == 1:
            spec['amount'] = [amount[0], unc_dict]
        elif len(amount) == 2 and isinstance(amount[1], dict):
            spec['amount'] = [amount[0], _merge_inline_uncertainty(amount[1], unc_dict)]
        return True
    return False


def _parse_esd_common(prop_elem):
    """Parse an evaluated-standard-deviation property from commonProperties.

    Returns a list of standalone entry dicts.
    """
    attrs = prop_elem.attrib
    reference = attrs.get('reference', '')
    kind = attrs.get('kind', '')
    units = attrs.get('units', '')

    base = {'reference': reference, 'kind': kind}
    for attr in ('sourcetype', 'method'):
        val = attrs.get(attr)
        if val:
            base[attr] = val

    entries = []
    if reference in ('composition', 'initial composition'):
        species_links = prop_elem.findall('speciesLink')
        values = prop_elem.findall('value')
        for sl, val_el in zip(species_links, values):
            entry = dict(base)
            spec = parse_species_link(sl)
            entry.update(spec)
            if units in ('ppm', 'ppb', 'percent'):
                conv_val, conv_units = normalize_comp_units(val_el.text.strip(), units)
                entry['value'] = [f'{conv_val} {conv_units}']
            else:
                entry['value'] = [_format_unc_value(_clean_numeric(val_el.text), units)]
            entries.append(entry)
    else:
        val_el = prop_elem.find('value')
        if val_el is not None:
            entry = dict(base)
            entry['value'] = [_format_unc_value(_clean_numeric(val_el.text), units)]
            entries.append(entry)
    return entries


def parse_common_properties(root, exp_type):
    common = {}
    pending_uncs = []  # uncertainty prop_elems to process in second pass
    pending_esds = []  # evaluated-standard-deviation prop_elems

    # First pass: collect scalar properties, compositions
    for prop_elem in root.findall('commonProperties/property'):
        name = prop_elem.attrib.get('name', '')

        if name == 'initial composition':
            comp = parse_initial_composition(prop_elem)
            if comp and comp.get('species'):
                import numpy as _np_cp
                total = 100.0 if comp.get('kind') == 'mole percent' else 1.0
                comp_sum = sum(sp['amount'][0] for sp in comp['species'] if sp.get('amount'))
                if not _np_cp.isclose(total, comp_sum, rtol=0.0, atol=total * 0.11):
                    # Partial CP composition (sum deviates >11% from expected total).
                    # Store for merging into per-dp compositions; don't use as standalone.
                    common['_partial_cp_composition'] = comp
                else:
                    common['composition'] = comp
            else:
                common['composition'] = comp
        elif name == 'equivalence ratio':
            val_el = prop_elem.find('value')
            if val_el is not None:
                common['equivalence-ratio'] = [f'{_clean_numeric(val_el.text)} dimensionless']
        elif name in SCALAR_COMMON_PROPS:
            val_el = prop_elem.find('value')
            units = prop_elem.attrib.get('units', '')
            units = _normalize_units(units)
            if val_el is not None:
                key = prop_name_to_key(name)
                common[key] = [f'{_clean_numeric(val_el.text)} {units}']
        elif name == 'uncertainty':
            pending_uncs.append(prop_elem)
        elif name == 'evaluated standard deviation':
            pending_esds.append(prop_elem)

    # Second pass: inline uncertainties
    inline_uncs = {}  # key → inline unc dict (for merging plus/minus pairs)
    pending_unc_entries = []  # unresolvable species uncertainties
    for prop_elem in pending_uncs:
        attrs = prop_elem.attrib
        reference = attrs.get('reference', '')
        kind = attrs.get('kind', '')
        units = attrs.get('units', '')
        bound = attrs.get('bound', '')
        sourcetype = attrs.get('sourcetype', '')

        target_key = _ref_to_property_key(reference)
        if target_key is not None and target_key in common:
            # Scalar-reference: convert to inline uncertainty on the property
            val_el = prop_elem.find('value')
            if val_el is not None:
                unc_dict = _build_inline_uncertainty(
                    kind, bound, _clean_numeric(val_el.text), units, sourcetype
                )
                if target_key in inline_uncs:
                    inline_uncs[target_key] = _merge_inline_uncertainty(
                        inline_uncs[target_key], unc_dict
                    )
                else:
                    inline_uncs[target_key] = unc_dict
        elif reference in ('composition', 'initial composition') and 'composition' in common:
            # Composition-reference: inline on species amount fields
            species_links = prop_elem.findall('speciesLink')
            values = prop_elem.findall('value')
            for sl, val_el in zip(species_links, values):
                spec = parse_species_link(sl)
                species_name = spec.get('species-name', '')
                raw_val = _clean_numeric(val_el.text)
                if not _attach_comp_uncertainty_inline(
                    common['composition'], species_name, kind, bound,
                    raw_val, units, sourcetype
                ):
                    # Species not in initial composition (e.g., measured species)
                    pending_unc_entries.append({
                        'reference': reference, 'kind': kind,
                        'units': units, 'bound': bound,
                        'sourcetype': sourcetype,
                        'value': raw_val,
                        'species-name': species_name,
                    })

    # Attach inline uncertainties to their property fields
    for key, unc_dict in inline_uncs.items():
        prop_val = common[key]
        if isinstance(prop_val, list) and len(prop_val) >= 1:
            common[key] = [prop_val[0], unc_dict]

    # Third pass: inline ESD
    pending_esd_entries = []  # unresolvable entries for post-merge
    for prop_elem in pending_esds:
        attrs = prop_elem.attrib
        reference = attrs.get('reference', '')
        kind = attrs.get('kind', '')
        units = attrs.get('units', '')
        sourcetype = attrs.get('sourcetype', '')
        method = attrs.get('method', '')

        target_key = _ref_to_property_key(reference)
        if target_key is not None and target_key in common:
            val_el = prop_elem.find('value')
            if val_el is not None:
                esd_fields = _build_inline_esd(
                    kind, _clean_numeric(val_el.text), units, sourcetype, method
                )
                _attach_metadata_to_property(common, target_key, esd_fields)
        elif reference in ('composition', 'initial composition') and 'composition' in common:
            species_links = prop_elem.findall('speciesLink')
            values = prop_elem.findall('value')
            for sl, val_el in zip(species_links, values):
                spec = parse_species_link(sl)
                species_name = spec.get('species-name', '')
                if not _attach_comp_esd_inline(
                    common['composition'], species_name, kind,
                    _clean_numeric(val_el.text), units, sourcetype, method
                ):
                    # Species not in initial composition (e.g., measured species)
                    pending_esd_entries.append({
                        'reference': reference, 'kind': kind,
                        'units': units, 'sourcetype': sourcetype,
                        'method': method,
                        'value': _clean_numeric(val_el.text),
                        'species-name': species_name,
                    })
        else:
            # Target property not in common (varies per datapoint)
            if reference in ('composition', 'initial composition'):
                # Composition ESDs that aren't in common yet — save for post-merge
                species_links = prop_elem.findall('speciesLink')
                values = prop_elem.findall('value')
                for sl, val_el in zip(species_links, values):
                    spec = parse_species_link(sl)
                    pending_esd_entries.append({
                        'reference': reference, 'kind': kind,
                        'units': units, 'sourcetype': sourcetype,
                        'method': method,
                        'value': _clean_numeric(val_el.text),
                        'species-name': spec.get('species-name', ''),
                    })
            elif target_key is not None:
                # Scalar ESD for a per-dp property — keep as metadata-only
                # in common-properties (no value, just the ESD dict)
                val_el = prop_elem.find('value')
                if val_el is not None:
                    esd_fields = _build_inline_esd(
                        kind, _clean_numeric(val_el.text), units, sourcetype, method
                    )
                    common[target_key] = [esd_fields]
            else:
                # Unknown reference — save for post-merge
                val_el = prop_elem.find('value')
                if val_el is not None:
                    pending_esd_entries.append({
                        'reference': reference, 'kind': kind,
                        'units': units, 'sourcetype': sourcetype,
                        'method': method,
                        'value': _clean_numeric(val_el.text),
                    })

    if pending_esd_entries:
        common['_pending_esd'] = pending_esd_entries

    if pending_unc_entries:
        common['_pending_unc'] = pending_unc_entries

    return common


def parse_ignition_type(root):
    elem = root.find('ignitionType')
    if elem is None:
        return None
    target = elem.attrib.get('target', '').rstrip(';').strip()
    ig_type = elem.attrib.get('type', '')
    target_map = {'OHEX': 'OHEX', 'CHEX': 'CHEX', 'P': 'pressure', 'T': 'temperature',
                  'OH*': 'OH*', 'CH*': 'CH*', 'CO2*': 'CO2'}
    target = target_map.get(target.upper(), target_map.get(target, target))
    # Map ReSpecTh ignition type names to PyKED schema values (mirrors converters.py)
    ign_type_map = {
        'baseline max intercept from d/dt': 'd/dt max extrapolated',
        'baseline min intercept from d/dt': 'd/dt min extrapolated',
    }
    ig_type = ign_type_map.get(ig_type, ig_type)
    result = {'target': target, 'type': ig_type}
    # Capture amount for relative concentration (fraction of peak at which ignition is detected)
    amount_str = elem.attrib.get('amount', '')
    if amount_str:
        try:
            result['amount'] = float(amount_str)
        except ValueError:
            pass
    return result


# ---------------------------------------------------------------------------
# DataGroup property definitions
# ---------------------------------------------------------------------------

def parse_datagroup_props(data_group):
    """Return {id: {name, units, species?, + uncertainty attrs}} for each <property>."""
    defs = {}
    for prop in data_group.findall('property'):
        pid = prop.attrib['id']
        entry = {
            'name': prop.attrib['name'],
            'units': prop.attrib.get('units', ''),
        }
        sl = prop.find('speciesLink')
        if sl is not None:
            entry['species'] = parse_species_link(sl)
        # Extra attributes for uncertainty / evaluated standard deviation
        for attr in ('reference', 'kind', 'bound', 'method', 'sourcetype'):
            val = prop.attrib.get(attr)
            if val:
                entry[attr] = val
        defs[pid] = entry
    return defs


# ---------------------------------------------------------------------------
# Composition builder from datapoint values
# ---------------------------------------------------------------------------

def build_composition(prop_defs, dp_elem):
    """Build a composition dict from composition columns in a datapoint."""
    entries = []  # [(spec_dict, value, kind)]
    for val_el in dp_elem:
        pid = val_el.tag
        if pid not in prop_defs:
            continue
        pdef = prop_defs[pid]
        if pdef['name'] != 'composition':
            continue
        spec = dict(pdef.get('species', {}))
        val, kind = normalize_comp_units(val_el.text, pdef['units'])
        if val < 0:
            # -1.0 is a sentinel for "below detection limit"; skip these species
            log.debug(f'Skipping species {spec.get("species-name", "?")} with negative '
                      f'value {val} (below detection limit)')
            continue
        entries.append((spec, val, kind))
    if not entries:
        return None
    target_kind, resolved = _reconcile_composition(entries)
    comp = {'kind': target_kind, 'species': []}
    for spec, val in resolved:
        spec['amount'] = [val]
        comp['species'].append(spec)
    return comp


def _add_balance_diluent(measured, initial_composition):
    """Top up measured-composition to sum to 1.0 using the diluent from initial_composition.

    For JSR/flow-reactor experiments only a subset of species are measured.
    The balance (typically N2 or Ar diluent) is inferred from the initial
    composition and added so the mole fractions sum to 1.0 as required by
    PyKED validation.

    Args:
        measured (dict): composition dict built by build_composition().
        initial_composition (dict | None): common-properties composition dict.

    Returns:
        dict: measured composition with balance species added if needed.
    """
    if measured is None or initial_composition is None:
        return measured

    kind = measured.get('kind', 'mole fraction')
    total = 100.0 if kind == 'mole percent' else 1.0
    current_sum = sum(sp['amount'][0] for sp in measured['species'])

    import numpy as np
    if np.isclose(total, current_sum):
        return measured  # already sums to 1.0

    measured_names = {sp['species-name'] for sp in measured['species']}

    # Find the diluent: species in initial_composition not already measured,
    # with the largest mole fraction (i.e. the main diluent, e.g. N2 or Ar).
    init_kind = initial_composition.get('kind', 'mole fraction')
    init_total = 100.0 if init_kind == 'mole percent' else 1.0
    candidates = [
        sp for sp in initial_composition.get('species', [])
        if sp['species-name'] not in measured_names
    ]
    if not candidates:
        return measured

    # Pick the dominant non-measured species
    diluent_spec = max(candidates, key=lambda s: s['amount'][0])
    balance = total - current_sum
    if balance <= 0:
        return measured

    # Build a minimal species entry (copy identifiers, set inferred amount)
    diluent_entry = {k: v for k, v in diluent_spec.items() if k != 'amount'}
    diluent_entry['amount'] = [round(balance, 8)]
    measured['species'].append(diluent_entry)
    return measured


def build_initial_composition(prop_defs, dp_elem, partial_cp_composition=None):
    """Build initial composition dict from 'initial composition' columns.

    If *partial_cp_composition* is given (a partial common-property composition
    that didn't sum to 1.0), its species are merged into the per-datapoint
    composition so the combined block sums correctly.
    """
    entries = []
    dp_species_names = set()
    for val_el in dp_elem:
        pid = val_el.tag
        if pid not in prop_defs:
            continue
        pdef = prop_defs[pid]
        if pdef['name'] != 'initial composition':
            continue
        spec = dict(pdef.get('species', {}))
        val, kind = normalize_comp_units(val_el.text, pdef['units'])
        entries.append((spec, val, kind))
        dp_species_names.add(spec.get('species-name', ''))
    if not entries:
        return None
    # Merge species from partial CP composition that aren't already in per-dp
    if partial_cp_composition and partial_cp_composition.get('species'):
        cp_kind = partial_cp_composition.get('kind', 'mole fraction')
        for sp in partial_cp_composition['species']:
            sname = sp.get('species-name', '')
            if sname and sname not in dp_species_names:
                spec_copy = {k: v for k, v in sp.items() if k != 'amount'}
                val = sp['amount'][0]
                entries.append((spec_copy, val, cp_kind))
    target_kind, resolved = _reconcile_composition(entries)
    comp = {'kind': target_kind, 'species': []}
    for spec, val in resolved:
        spec['amount'] = [val]
        comp['species'].append(spec)
    return comp


def build_uncertainty_entries(dg_defs, dp_elem, dp=None):
    """Build uncertainty and ESD entries from datapoint columns, inlining both.

    Uncertainty entries are inlined on the target property in dp[key].
    ESD entries are inlined directly on dp properties.

    Returns a list of standalone uncertainty entries that could not be inlined.
    """
    standalone_unc = []
    inline_uncs = {}  # target_key → inline unc dict

    for val_el in dp_elem:
        pid = val_el.tag
        if pid not in dg_defs:
            continue
        pdef = dg_defs[pid]
        name = pdef['name']

        if name not in ('uncertainty', 'evaluated standard deviation'):
            continue

        ref = pdef.get('reference', '')
        kind = pdef.get('kind', '')
        units = pdef.get('units', '')

        if name == 'evaluated standard deviation':
            # Inline ESD directly on the target property
            sourcetype = pdef.get('sourcetype')
            method = pdef.get('method')
            target_key = _ref_to_property_key(ref, dg_defs)
            if target_key is not None and dp is not None and target_key in dp:
                esd_fields = _build_inline_esd(
                    kind, _clean_numeric(val_el.text), units, sourcetype, method
                )
                _attach_metadata_to_property(dp, target_key, esd_fields)
            elif ref in ('composition', 'initial composition') and dp is not None:
                species_name = pdef.get('species', {}).get('species-name', '')
                if species_name:
                    for comp_key in ('composition', 'measured-composition'):
                        comp_block = dp.get(comp_key)
                        if comp_block and _attach_comp_esd_inline(
                            comp_block, species_name, kind,
                            _clean_numeric(val_el.text), units, sourcetype, method
                        ):
                            break
            continue

        # name == 'uncertainty'
        target_key = _ref_to_property_key(ref, dg_defs)
        sourcetype = pdef.get('sourcetype', '')
        if target_key is not None and dp is not None and target_key in dp:
            # Scalar reference: build inline uncertainty
            bound = pdef.get('bound', '')
            unc_dict = _build_inline_uncertainty(
                kind, bound, _clean_numeric(val_el.text), units, sourcetype
            )
            if target_key in inline_uncs:
                inline_uncs[target_key] = _merge_inline_uncertainty(
                    inline_uncs[target_key], unc_dict
                )
            else:
                inline_uncs[target_key] = unc_dict
        elif ref in ('composition', 'initial composition') and dp is not None:
            # Composition reference: try to inline on species amount fields
            species_name = pdef.get('species', {}).get('species-name', '')
            bound = pdef.get('bound', '')
            raw_val = _clean_numeric(val_el.text)
            inlined = False
            if species_name:
                for comp_key in ('composition', 'measured-composition'):
                    comp_block = dp.get(comp_key)
                    if comp_block and _attach_comp_uncertainty_inline(
                        comp_block, species_name, kind, bound, raw_val, units,
                        sourcetype
                    ):
                        inlined = True
                        break
            if not inlined:
                log.debug(f'Could not inline composition uncertainty for {species_name}')
        else:
            log.debug(f'Could not inline uncertainty for reference={ref}')

    # Attach inline uncertainties to the datapoint property fields
    if dp is not None:
        for key, unc_dict in inline_uncs.items():
            prop_val = dp[key]
            if isinstance(prop_val, list) and len(prop_val) >= 1:
                dp[key] = [prop_val[0], unc_dict]

    return standalone_unc


# ---------------------------------------------------------------------------
# Per-experiment-type datapoint parsers
# ---------------------------------------------------------------------------

def _scalar_value(val_text, units):
    """Build a scalar value+unit list entry like ['700 K']."""
    units = _normalize_units(units)
    return [f'{_clean_numeric(val_text)} {units}']


def parse_idt_datapoints(root, dg, dg_defs, common):
    """Ignition delay: pressure, temperature, ignition-delay per point.
    Additional dataGroups may contain volume/pressure/temperature histories.
    """
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        comp = build_composition(dg_defs, dp_el)
        if comp:
            dp['composition'] = comp
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('composition', 'uncertainty', 'evaluated standard deviation'):
                continue
            if name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)

    # Handle additional dataGroups (volume/pressure/temperature time histories)
    all_dgs = root.findall('dataGroup')
    if len(all_dgs) > 1:
        extra_dgs = all_dgs[1:]
        # If number of extra dataGroups matches number of datapoints, assign 1:1
        # (RCM pattern: each condition has its own volume-time trace).
        # Otherwise assign all histories to datapoints[0].
        if len(extra_dgs) == len(datapoints):
            dp_targets = list(range(len(datapoints)))
        else:
            # Assign sequentially up to min(dgs, dps); skip extras (target=-1)
            n = min(len(extra_dgs), len(datapoints))
            dp_targets = list(range(n)) + [-1] * (len(extra_dgs) - n)

        for idx_dg, extra_dg in enumerate(extra_dgs):
            edefs = parse_datagroup_props(extra_dg)
            time_tag = None
            quant_info = []  # [(tag, type_name, units)]
            for pid, pdef in edefs.items():
                if pdef['name'] == 'time':
                    time_tag = pid
                elif pdef['name'] in ('volume', 'temperature', 'pressure'):
                    quant_info.append((pid, pdef['name'], pdef['units']))
            if time_tag is None or not quant_info:
                continue
            time_units = edefs[time_tag]['units']
            histories = [
                {
                    'time': {'units': time_units, 'column': 0},
                    'quantity': {'units': qi[2], 'column': 1},
                    'type': qi[1],
                    'values': [],
                }
                for qi in quant_info
            ]
            for dp_el in extra_dg.findall('dataPoint'):
                t_val = None
                q_vals = {}
                for val_el in dp_el:
                    if val_el.tag == time_tag:
                        t_val = float(val_el.text)
                    else:
                        for qi in quant_info:
                            if val_el.tag == qi[0]:
                                q_vals[qi[1]] = float(val_el.text)
                if t_val is not None:
                    for h in histories:
                        if h['type'] in q_vals:
                            h['values'].append(_FlowList([t_val, q_vals[h['type']]]))
            target = dp_targets[idx_dg]
            if histories[0]['values'] and target >= 0:
                datapoints[target].setdefault('time-histories', []).extend(histories)

    return datapoints


def parse_lbv_datapoints(dg, dg_defs, common):
    """Laminar burning velocity: composition, equivalence-ratio, LBV per point."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        comp = build_composition(dg_defs, dp_el)
        if comp:
            dp['composition'] = comp
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name == 'composition':
                continue
            elif name == 'equivalence ratio':
                dp['equivalence-ratio'] = [f'{_clean_numeric(val_el.text)} dimensionless']
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


def parse_jsr_datapoints(dg, dg_defs, common):
    """JSR: temperature varies, composition is measured outlet concentration."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        init_comp = build_initial_composition(dg_defs, dp_el, common.get('_partial_cp_composition'))
        if init_comp:
            dp['composition'] = init_comp
        measured = build_composition(dg_defs, dp_el)
        if measured:
            ref_comp = (init_comp
                        or common.get('composition')
                        or common.get('_partial_cp_composition'))
            measured = _add_balance_diluent(measured, ref_comp)
            dp['measured-composition'] = measured
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('composition', 'initial composition',
                        'uncertainty', 'evaluated standard deviation'):
                continue
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


def parse_ctpm_datapoints(dg, dg_defs, common):
    """Concentration time profile: tabular (time, species...) → single datapoint
    with concentration-profiles list.
    """
    time_id = None
    species_cols = []  # [(id, species_info, units)]
    for pid, pdef in dg_defs.items():
        if pdef['name'] == 'time':
            time_id = pid
        elif pdef['name'] in ('composition', 'concentration') and 'species' in pdef:
            species_cols.append((pid, pdef['species'], pdef['units']))

    if time_id is None or not species_cols:
        return []

    time_units = dg_defs[time_id]['units']

    # Collect all rows
    rows = []
    for dp_el in dg.findall('dataPoint'):
        row = {}
        for val_el in dp_el:
            row[val_el.tag] = val_el.text
        rows.append(row)

    # Build concentration profiles per species
    profiles = []
    for sid, spec_info, units in species_cols:
        profile = {'species-name': spec_info.get('species-name', '')}
        if 'InChI' in spec_info:
            profile['InChI'] = spec_info['InChI']

        # Determine if we need to convert ppm/ppb/percent → mole fraction
        needs_conv = units in ('ppm', 'ppb', 'percent')
        if needs_conv:
            _, conv_units = normalize_comp_units('1', units)
        else:
            conv_units = units

        profile['quantity'] = {'units': conv_units}
        profile['time'] = {'units': time_units}
        profile['values'] = []
        for row in rows:
            t_val = float(row.get(time_id, 0))
            c_raw = float(row.get(sid, 0))
            if needs_conv:
                c_val, _ = normalize_comp_units(str(c_raw), units)
            else:
                c_val = c_raw
            profile['values'].append(_FlowList([t_val, c_val]))
        profiles.append(profile)

    return [{'concentration-profiles': profiles}]


def parse_ocm_datapoints(dg, dg_defs, common):
    """Outlet concentration: temperature & flow rate vary, measured compositions."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        init_comp = build_initial_composition(dg_defs, dp_el, common.get('_partial_cp_composition'))
        if init_comp:
            dp['composition'] = init_comp
        measured = build_composition(dg_defs, dp_el)
        if measured:
            ref_comp = (init_comp
                        or common.get('composition')
                        or common.get('_partial_cp_composition'))
            measured = _add_balance_diluent(measured, ref_comp)
            dp['measured-composition'] = measured
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('composition', 'initial composition',
                        'uncertainty', 'evaluated standard deviation'):
                continue
            elif name == 'equivalence ratio':
                dp['equivalence-ratio'] = [f'{_clean_numeric(val_el.text)} dimensionless']
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


def parse_bsfsm_datapoints(dg, dg_defs, common):
    """Burner stabilised flame speciation: distance varies, measured compositions."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        measured = build_composition(dg_defs, dp_el)
        if measured:
            ref_comp = common.get('composition')
            measured = _add_balance_diluent(measured, ref_comp)
            dp['measured-composition'] = measured
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('composition', 'uncertainty', 'evaluated standard deviation'):
                continue
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


# ---------------------------------------------------------------------------
# Reaction parsing (kdetermination files)
# ---------------------------------------------------------------------------

def parse_reactions(root):
    """Parse <reaction> elements → list of reaction dicts."""
    reactions = []
    for rxn in root.findall('reaction'):
        entry = {
            'preferred-key': rxn.attrib.get('preferredKey', ''),
        }
        order = rxn.attrib.get('order')
        if order:
            try:
                entry['order'] = int(order)
            except ValueError:
                entry['order'] = order
        bulk_gas = rxn.attrib.get('bulkgas')
        if bulk_gas:
            entry['bulk-gas'] = bulk_gas

        reactants = []
        for i in range(1, 10):
            r = rxn.findtext(f'reactant{i}')
            if r:
                reactants.append(r.strip())
            else:
                break
        if reactants:
            entry['reactants'] = reactants

        products = []
        for i in range(1, 10):
            p = rxn.findtext(f'product{i}')
            if p:
                products.append(p.strip())
            else:
                break
        if products:
            entry['products'] = products

        reactions.append(entry)
    return reactions


# ---------------------------------------------------------------------------
# kdetermination datapoint parser
# ---------------------------------------------------------------------------

def parse_kdet_datapoints(dg, dg_defs, common):
    """Rate coefficient / branching ratio: temperature, rate-coefficient/branching-ratio,
    optional pressure per point."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('uncertainty', 'evaluated standard deviation'):
                continue
            if name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


# ---------------------------------------------------------------------------
# tdetermination datapoint parser
# ---------------------------------------------------------------------------

def parse_tdet_datapoints(dg, dg_defs, common):
    """Thermochemical data: temperature and thermodynamic properties per point."""
    datapoints = []
    for dp_el in dg.findall('dataPoint'):
        dp = {}
        for val_el in dp_el:
            pid = val_el.tag
            if pid not in dg_defs:
                continue
            pdef = dg_defs[pid]
            name = pdef['name']
            if name in ('uncertainty', 'evaluated standard deviation'):
                continue
            if name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        datapoints.append(dp)
    return datapoints


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

PARSERS = {
    'ignition delay': 'idt',
    'laminar burning velocity measurement': 'lbv',
    'jet stirred reactor measurement': 'jsr',
    'concentration time profile measurement': 'ctpm',
    'outlet concentration measurement': 'ocm',
    'burner stabilized flame speciation measurement': 'bsfsm',
}


def convert_file(xml_path, original_filename=None):
    """Convert a single ReSpecTh XML file → ChemKED property dict (or None).

    Supports <experiment>, <kdetermination>, and <tdetermination> root elements.

    Parameters
    ----------
    xml_path : str
        Path to the XML file on disk.
    original_filename : str, optional
        The original filename to record in the ``reference.detail`` field.
        Defaults to ``os.path.basename(xml_path)``.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    if root.tag == 'experiment':
        try:
            return _convert_file_inner(root, xml_path, original_filename)
        except UnsupportedUnitsError as e:
            log.info(f'Skipping {os.path.basename(xml_path)}: {e}')
            return None
    elif root.tag == 'kdetermination':
        return _convert_kdetermination(root, xml_path, original_filename)
    elif root.tag == 'tdetermination':
        return _convert_tdetermination(root, xml_path, original_filename)
    else:
        return None


def _convert_file_inner(root, xml_path, original_filename=None):

    xml_filename = original_filename or os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)
    props['file-type'] = 'experiment'

    exp_type, apparatus = parse_experiment_kind(root)
    props['experiment-type'] = exp_type
    props['apparatus'] = apparatus

    # Method and comments
    method = (root.findtext('method') or '').strip()
    if method:
        props['method'] = method

    comments = []
    for c_el in root.findall('comment'):
        if c_el.text and c_el.text.strip():
            comments.append(c_el.text.strip())
    if comments:
        props['comments'] = comments

    common = parse_common_properties(root, exp_type)
    props['common-properties'] = common

    if exp_type == 'ignition delay':
        ign_type = parse_ignition_type(root)
        if ign_type:
            common['ignition-type'] = ign_type

    # Parse main dataGroup
    all_dgs = root.findall('dataGroup')
    if not all_dgs:
        raise ValueError('No dataGroup found')

    dg = all_dgs[0]
    dg_defs = parse_datagroup_props(dg)

    kind = PARSERS[exp_type]
    if kind == 'idt':
        props['datapoints'] = parse_idt_datapoints(root, dg, dg_defs, common)
    elif kind == 'lbv':
        props['datapoints'] = parse_lbv_datapoints(dg, dg_defs, common)
    elif kind == 'jsr':
        props['datapoints'] = parse_jsr_datapoints(dg, dg_defs, common)
    elif kind == 'ctpm':
        props['datapoints'] = parse_ctpm_datapoints(dg, dg_defs, common)
    elif kind == 'ocm':
        props['datapoints'] = parse_ocm_datapoints(dg, dg_defs, common)
    elif kind == 'bsfsm':
        props['datapoints'] = parse_bsfsm_datapoints(dg, dg_defs, common)

    if not props.get('datapoints'):
        raise ValueError('No datapoints parsed')

    # Apply common properties to each datapoint (matches existing PyKED convention)
    for dp in props['datapoints']:
        for key, val in common.items():
            if key not in dp:
                dp[key] = val

    # Post-merge: inline any remaining standalone scalar uncertainties
    _UNC_KEYS = ('uncertainty', 'upper-uncertainty', 'lower-uncertainty')

    def _extract_unc_from_entry(entry):
        """Extract (bound_key, value_str, units) from a standalone entry."""
        for bk in _UNC_KEYS:
            if bk in entry:
                raw = entry[bk]
                val_str = raw[0] if isinstance(raw, list) else str(raw)
                parts = val_str.split(' ', 1)
                return bk, parts[0], (parts[1] if len(parts) > 1 else '')
        return None, '', ''

    for dp in props['datapoints']:
        # Inline remaining standalone uncertainty entries
        for entry in dp.pop('uncertainty', []):
            ref = entry.get('reference', '')
            target_key = _ref_to_property_key(ref)
            sourcetype = entry.get('sourcetype', '')
            if target_key and target_key in dp:
                unc_kind = entry.get('kind', '')
                bound_key, val_str, unc_units = _extract_unc_from_entry(entry)
                if bound_key is None:
                    continue
                unc_dict = {'uncertainty-type': unc_kind}
                unc_dict[bound_key] = _format_unc_value(val_str, unc_units, unc_kind)
                if sourcetype:
                    unc_dict['uncertainty-sourcetype'] = sourcetype
                prop_val = dp[target_key]
                if isinstance(prop_val, list) and len(prop_val) >= 1:
                    if len(prop_val) == 2 and isinstance(prop_val[1], dict):
                        dp[target_key] = [prop_val[0], _merge_inline_uncertainty(prop_val[1], unc_dict)]
                    else:
                        dp[target_key] = [prop_val[0], unc_dict]
            elif ref in ('composition', 'initial composition'):
                species_name = entry.get('species-name', '')
                unc_kind = entry.get('kind', '')
                bound_key, val_str, unc_units = _extract_unc_from_entry(entry)
                bound = {'upper-uncertainty': 'plus',
                         'lower-uncertainty': 'minus'}.get(bound_key, 'plusminus')
                if species_name and bound_key:
                    for comp_key in ('composition', 'measured-composition'):
                        comp_block = dp.get(comp_key)
                        if comp_block and _attach_comp_uncertainty_inline(
                            comp_block, species_name, unc_kind, bound,
                            val_str, unc_units, sourcetype
                        ):
                            break

        # Inline pending ESD from common properties
        for esd_entry in dp.pop('_pending_esd', []):
            reference = esd_entry['reference']
            target_key = _ref_to_property_key(reference)
            if target_key and target_key in dp:
                esd_fields = _build_inline_esd(
                    esd_entry['kind'], esd_entry['value'], esd_entry['units'],
                    esd_entry.get('sourcetype'), esd_entry.get('method')
                )
                _attach_metadata_to_property(dp, target_key, esd_fields)
            elif reference in ('composition', 'initial composition'):
                species_name = esd_entry.get('species-name', '')
                if species_name:
                    for comp_key in ('composition', 'measured-composition'):
                        comp_block = dp.get(comp_key)
                        if comp_block and _attach_comp_esd_inline(
                            comp_block, species_name,
                            esd_entry['kind'], esd_entry['value'],
                            esd_entry['units'],
                            esd_entry.get('sourcetype'), esd_entry.get('method')
                        ):
                            break

        # Inline pending uncertainties from common properties (measured species)
        for unc_entry in dp.pop('_pending_unc', []):
            ref = unc_entry.get('reference', '')
            if ref in ('composition', 'initial composition'):
                species_name = unc_entry.get('species-name', '')
                unc_kind = unc_entry.get('kind', '')
                bound = unc_entry.get('bound', 'plusminus')
                raw_val = unc_entry.get('value', '')
                unc_units = unc_entry.get('units', '')
                sourcetype = unc_entry.get('sourcetype', '')
                if species_name:
                    for comp_key in ('composition', 'measured-composition'):
                        comp_block = dp.get(comp_key)
                        if comp_block and _attach_comp_uncertainty_inline(
                            comp_block, species_name, unc_kind, bound,
                            raw_val, unc_units, sourcetype
                        ):
                            break

    # Clean up common properties — remove temporary keys
    common.pop('uncertainty', None)
    common.pop('evaluated-standard-deviation', None)
    common.pop('_pending_esd', None)
    common.pop('_pending_unc', None)
    common.pop('_partial_cp_composition', None)

    return props


# ---------------------------------------------------------------------------
# kdetermination conversion
# ---------------------------------------------------------------------------

def _convert_kdetermination(root, xml_path, original_filename=None):
    """Convert a <kdetermination> XML file to a ChemKED-style property dict."""
    xml_filename = original_filename or os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)
    props['file-type'] = 'kdetermination'
    props['experiment-type'] = 'rate coefficient'

    # Parse reactions — schema expects 'reaction' (string) and 'bulk-gas' (string)
    reactions = parse_reactions(root)
    if reactions:
        primary = reactions[0]
        if primary.get('preferred-key'):
            props['reaction'] = primary['preferred-key']
        if primary.get('bulk-gas'):
            props['bulk-gas'] = primary['bulk-gas']

    # Method and apparatus
    method = (root.findtext('method') or '').strip()
    if method:
        props['method'] = method
    # Map method text to apparatus kind
    _method_to_apparatus = {
        'shock tube': 'shock tube',
        'shock wave': 'shock tube',
        'flow tube': 'flow reactor',
        'flow reactor': 'flow reactor',
        'static reactor': 'flow reactor',
        'stirred reactor': 'stirred reactor',
        'flame': 'flame',
    }
    apparatus_kind = _method_to_apparatus.get(method.lower(), 'shock tube')
    props['apparatus'] = {'kind': apparatus_kind}

    comments = []
    for c_el in root.findall('comment'):
        if c_el.text and c_el.text.strip():
            comments.append(c_el.text.strip())
    if comments:
        props['comments'] = comments

    # Common properties (parsed the same way as experiments)
    common = parse_common_properties(root, 'rate coefficient')
    props['common-properties'] = common

    # Parse dataGroup
    all_dgs = root.findall('dataGroup')
    if not all_dgs:
        raise ValueError('No dataGroup found')

    dg = all_dgs[0]
    dg_defs = parse_datagroup_props(dg)

    props['datapoints'] = parse_kdet_datapoints(dg, dg_defs, common)

    if not props.get('datapoints'):
        raise ValueError('No datapoints parsed')

    # Apply common properties to each datapoint
    for dp in props['datapoints']:
        for key, val in common.items():
            if key not in dp:
                dp[key] = val

    # Post-merge inline remaining uncertainties (same as experiment)
    _UNC_KEYS = ('uncertainty', 'upper-uncertainty', 'lower-uncertainty')

    def _extract_unc_from_entry(entry):
        for bk in _UNC_KEYS:
            if bk in entry:
                raw = entry[bk]
                val_str = raw[0] if isinstance(raw, list) else str(raw)
                parts = val_str.split(' ', 1)
                return bk, parts[0], (parts[1] if len(parts) > 1 else '')
        return None, '', ''

    for dp in props['datapoints']:
        for entry in dp.pop('uncertainty', []):
            ref = entry.get('reference', '')
            target_key = _ref_to_property_key(ref)
            sourcetype = entry.get('sourcetype', '')
            if target_key and target_key in dp:
                unc_kind = entry.get('kind', '')
                bound_key, val_str, unc_units = _extract_unc_from_entry(entry)
                if bound_key is None:
                    continue
                unc_dict = {'uncertainty-type': unc_kind}
                unc_dict[bound_key] = _format_unc_value(val_str, unc_units, unc_kind)
                if sourcetype:
                    unc_dict['uncertainty-sourcetype'] = sourcetype
                prop_val = dp[target_key]
                if isinstance(prop_val, list) and len(prop_val) >= 1:
                    if len(prop_val) == 2 and isinstance(prop_val[1], dict):
                        dp[target_key] = [prop_val[0], _merge_inline_uncertainty(prop_val[1], unc_dict)]
                    else:
                        dp[target_key] = [prop_val[0], unc_dict]

        for esd_entry in dp.pop('_pending_esd', []):
            reference = esd_entry['reference']
            target_key = _ref_to_property_key(reference)
            if target_key and target_key in dp:
                esd_fields = _build_inline_esd(
                    esd_entry['kind'], esd_entry['value'], esd_entry['units'],
                    esd_entry.get('sourcetype'), esd_entry.get('method')
                )
                _attach_metadata_to_property(dp, target_key, esd_fields)

    common.pop('uncertainty', None)
    common.pop('evaluated-standard-deviation', None)
    common.pop('_pending_esd', None)
    common.pop('_pending_unc', None)
    common.pop('_partial_cp_composition', None)

    return props


# ---------------------------------------------------------------------------
# tdetermination conversion
# ---------------------------------------------------------------------------

def _convert_tdetermination(root, xml_path, original_filename=None):
    """Convert a <tdetermination> XML file to a ChemKED-style property dict."""
    xml_filename = original_filename or os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)
    props['file-type'] = 'tdetermination'
    props['experiment-type'] = 'thermochemical'

    # Parse reactions (tdetermination may have species/reaction info)
    reactions = parse_reactions(root)
    if reactions:
        primary = reactions[0]
        if primary.get('preferred-key'):
            props['reaction'] = primary['preferred-key']
        if primary.get('bulk-gas'):
            props['bulk-gas'] = primary['bulk-gas']

    method = (root.findtext('method') or '').strip()
    if method:
        props['method'] = method

    comments = []
    for c_el in root.findall('comment'):
        if c_el.text and c_el.text.strip():
            comments.append(c_el.text.strip())
    if comments:
        props['comments'] = comments

    common = parse_common_properties(root, 'thermochemical')
    props['common-properties'] = common

    all_dgs = root.findall('dataGroup')
    if not all_dgs:
        raise ValueError('No dataGroup found')

    dg = all_dgs[0]
    dg_defs = parse_datagroup_props(dg)

    props['datapoints'] = parse_tdet_datapoints(dg, dg_defs, common)

    if not props.get('datapoints'):
        raise ValueError('No datapoints parsed')

    for dp in props['datapoints']:
        for key, val in common.items():
            if key not in dp:
                dp[key] = val

    common.pop('uncertainty', None)
    common.pop('evaluated-standard-deviation', None)
    common.pop('_pending_esd', None)
    common.pop('_pending_unc', None)
    common.pop('_partial_cp_composition', None)

    return props


# ---------------------------------------------------------------------------
# Output path logic
# ---------------------------------------------------------------------------

def get_output_path(xml_path, input_dir, output_dir, reference):
    """Determine output YAML path: output_dir/fuel/Author_Year/filename.yaml"""
    rel = os.path.relpath(xml_path, input_dir)
    parts = Path(rel).parts

    fuel = parts[0] if len(parts) > 1 else 'unknown'

    authors = reference.get('authors', [])
    year = reference.get('year', 'unknown')
    last_name = first_author_last_name(authors)
    ref_dir = f'{last_name}_{year}'

    yaml_name = Path(parts[-1]).stem + '.yaml'
    return os.path.join(output_dir, fuel, ref_dir, yaml_name)


# ---------------------------------------------------------------------------
# Batch conversion
# ---------------------------------------------------------------------------

def batch_convert(input_dir, output_dir, dry_run=False):
    stats = {'total': 0, 'success': 0, 'skipped': 0, 'errors': 0, 'validation_errors': 0}
    errors_log = []
    validation_errors_log = []
    type_counts = {}

    xml_files = sorted(Path(input_dir).rglob('*.xml'))
    stats['total'] = len(xml_files)
    log.info(f'Found {len(xml_files)} XML files in {input_dir}')

    for xml_path in xml_files:
        xml_str = str(xml_path)
        try:
            result = convert_file(xml_str)
            if result is None:
                stats['skipped'] += 1
                continue

            exp_type = result['experiment-type']
            type_counts[exp_type] = type_counts.get(exp_type, 0) + 1

            out_path = get_output_path(xml_str, input_dir, output_dir,
                                       result['reference'])

            if dry_run:
                log.debug(f'  Would write: {out_path}')
                stats['success'] += 1
            else:
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                result.pop('file-type', None)
                with open(out_path, 'w') as f:
                    yaml_dump(result, f)

                # Post-write PyKED validation
                if _ChemKED is not None:
                    try:
                        _ChemKED(yaml_file=out_path)
                        stats['success'] += 1
                    except Exception as ve:
                        stats['validation_errors'] += 1
                        validation_errors_log.append((xml_str, str(ve)))
                        log.warning(f'Validation error in {xml_path.name}: {ve}')
                else:
                    stats['success'] += 1

        except Exception as e:
            stats['errors'] += 1
            errors_log.append((xml_str, str(e)))
            log.warning(f'Error converting {xml_path.name}: {e}')

    # Summary
    log.info('')
    log.info('=== Conversion Summary ===')
    log.info(f'Total files:       {stats["total"]}')
    log.info(f'Converted:         {stats["success"]}')
    log.info(f'Skipped:           {stats["skipped"]}')
    log.info(f'Conversion errors: {stats["errors"]}')
    log.info(f'Validation errors: {stats["validation_errors"]}')
    log.info('')
    log.info('By experiment type:')
    for t, c in sorted(type_counts.items()):
        log.info(f'  {t}: {c}')

    if errors_log:
        log.info('')
        log.info('First 20 conversion errors:')
        for path, err in errors_log[:20]:
            log.info(f'  {os.path.basename(path)}: {err}')

    if validation_errors_log:
        log.info('')
        log.info('First 20 validation errors:')
        for path, err in validation_errors_log[:20]:
            log.info(f'  {os.path.basename(path)}: {err}')

    return stats, errors_log, validation_errors_log


def convert_single(xml_path, output_path=None):
    """Convert a single file and optionally write output."""
    result = convert_file(xml_path)
    if result is None:
        log.info(f'Skipped (unsupported root element): {xml_path}')
        return

    if output_path is None:
        output_path = Path(xml_path).stem + '.yaml'

    file_type = result.pop('file-type', 'experiment')
    with open(output_path, 'w') as f:
        yaml_dump(result, f)
    log.info(f'Converted ({file_type}): {xml_path} → {output_path}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Batch convert ReSpecTh v2.3/v2.4 XML files to ChemKED YAML'
    )
    parser.add_argument('--input-dir', '-i', default='ReSpecTh/indirect',
                        help='Input directory with ReSpecTh XML files '
                             '(default: ReSpecTh/indirect)')
    parser.add_argument('--output-dir', '-o', default='ChemKED-database',
                        help='Output directory for ChemKED YAML files '
                             '(default: ChemKED-database)')
    parser.add_argument('--file', '-f', default=None,
                        help='Convert a single XML file instead of batch')
    parser.add_argument('--output-file', default=None,
                        help='Output path for single-file mode')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Parse but do not write files')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.file:
        convert_single(args.file, args.output_file)
    else:
        batch_convert(args.input_dir, args.output_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
