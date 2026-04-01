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


# Custom YAML dumper that preserves dict insertion order
class _OrderedDumper(yaml.Dumper):
    pass

def _dict_representer(dumper, data):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                   data.items())

_OrderedDumper.add_representer(dict, _dict_representer)


class _FlowList(list):
    """List subclass that signals the YAML dumper to use flow style."""
    pass

def _flow_list_representer(dumper, data):
    return dumper.represent_sequence(yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG,
                                    data, flow_style=True)

_OrderedDumper.add_representer(_FlowList, _flow_list_representer)


def yaml_dump(data, stream):
    """Dump data to YAML preserving dict key order."""
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
    """Parse 'Last, First and Last, First ...' → [{'name': 'First Last'}, ...]"""
    authors = []
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
    text = text.strip()
    try:
        val = float(text)
        if val != val:  # NaN
            return text
        # Integer-valued: format as integer string
        if val == int(val) and '.' not in text and 'e' not in text.lower():
            return str(int(val))
        # Otherwise format cleanly (strips trailing zeros, avoids float noise)
        return f'{val:.12g}'
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
        return float(f'{val * 1e-6:.10g}'), 'mole fraction'
    elif units == 'ppb':
        return float(f'{val * 1e-9:.10g}'), 'mole fraction'
    else:
        raise UnsupportedUnitsError(
            f'Composition units {units!r} not supported. '
            'Must be one of: mole fraction, mass fraction, mole percent, '
            'percent, ppm, or ppb.'
        )


def _reconcile_composition(entries):
    """Pick a single kind for the composition block.

    *entries*: list of (spec_dict, value, kind) tuples.
    Returns (target_kind, [(spec_dict, value)]).
    After normalisation, all entries should share the same kind.
    If mixed, the dominant kind is used and a warning is logged.
    """
    kinds = set(e[2] for e in entries)
    if len(kinds) == 1:
        k = kinds.pop()
        return k, [(e[0], e[1]) for e in entries]
    # Mixed units – pick dominant kind, pass values through as-is
    kind_counts = Counter(e[2] for e in entries)
    dominant = kind_counts.most_common(1)[0][0]
    log.warning(f'Mixed composition units {dict(kind_counts)}; using {dominant!r}')
    return dominant, [(e[0], e[1]) for e in entries]


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

    file_doi = (root.findtext('fileDOI') or '').strip()
    if file_doi:
        props['file-doi'] = file_doi

    # ReSpecTh version
    rsv = root.find('ReSpecThVersion')
    if rsv is not None:
        major = (rsv.findtext('major') or '').strip()
        minor = (rsv.findtext('minor') or '').strip()
        if major:
            props['respecth-version'] = f'{major}.{minor}' if minor else major

    first_pub = (root.findtext('firstPublicationDate') or '').strip()
    if first_pub:
        props['first-publication-date'] = first_pub

    last_mod = (root.findtext('lastModificationDate') or '').strip()
    if last_mod:
        props['last-modification-date'] = last_mod

    return props


def parse_reference(root, xml_filename):
    ref = {}
    bib = root.find('bibliographyLink')
    if bib is None:
        ref['detail'] = f'Converted from ReSpecTh XML file {xml_filename}'
        return ref

    doi_el = bib.find('referenceDOI')
    if doi_el is not None and doi_el.text:
        ref['doi'] = doi_el.text.strip()

    # Location, table, figure from bibliographyLink attributes/elements
    location = (bib.findtext('location') or '').strip()
    if location:
        ref['location'] = location
    table = (bib.findtext('table') or '').strip()
    if table:
        ref['table'] = table
    figure = (bib.findtext('figure') or '').strip()
    if figure:
        ref['figure'] = figure

    details = bib.find('details')
    if details is not None:
        auth = (details.findtext('author') or '').strip()
        if auth:
            ref['authors'] = parse_author_string(auth)
        journal = (details.findtext('journal') or '').strip()
        if journal:
            ref['journal'] = decode_latex(journal)
        title = (details.findtext('title') or '').strip()
        if title:
            ref['title'] = decode_latex(title)
        year = (details.findtext('year') or '').strip()
        if year:
            ref['year'] = int(year)
        vol = (details.findtext('volume') or '').strip()
        if vol:
            try:
                ref['volume'] = int(vol)
            except ValueError:
                ref['volume'] = vol
        pages = (details.findtext('pages') or '').strip()
        if pages:
            ref['pages'] = pages
        number = (details.findtext('number') or '').strip()
        if number:
            ref['number'] = number
        pub_type = (details.findtext('type') or '').strip()
        if pub_type:
            ref['publication-type'] = pub_type

    # Fallback: use <description>
    if not ref.get('authors'):
        desc = (bib.findtext('description') or '').strip()
        if desc:
            ref['detail'] = desc

    prefix = ref.get('detail', '')
    ref['detail'] = (prefix + ' ' if prefix else '') + \
                    f'Converted from ReSpecTh XML file {xml_filename}'
    return ref


# ---------------------------------------------------------------------------
# Experiment kind & apparatus
# ---------------------------------------------------------------------------

def parse_experiment_kind(root):
    exp_text = (root.findtext('experimentType') or '').strip().lower()
    exp_type = EXP_TYPE_MAP.get(exp_text)
    if exp_type is None:
        raise ValueError(f'Unknown experiment type: {root.findtext("experimentType")}')

    apparatus = {'kind': '', 'institution': '', 'facility': ''}
    kind_el = root.find('apparatus/kind')
    if kind_el is not None and kind_el.text:
        apparatus['kind'] = kind_el.text.strip()
    modes = root.findall('apparatus/mode')
    if modes and modes[0].text:
        apparatus['mode'] = modes[0].text.strip()

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
    for key in ('uncertainty', 'upper-uncertainty', 'lower-uncertainty',
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
            common['composition'] = parse_initial_composition(prop_elem)
        elif name == 'equivalence ratio':
            val_el = prop_elem.find('value')
            if val_el is not None:
                common['equivalence-ratio'] = [f'{_clean_numeric(val_el.text)} dimensionless']
        elif name in SCALAR_COMMON_PROPS:
            val_el = prop_elem.find('value')
            units = prop_elem.attrib.get('units', '')
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
            # Can't resolve yet — save for post-merge
            if reference in ('composition', 'initial composition'):
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
            else:
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
    target = elem.attrib.get('target', '')
    ig_type = elem.attrib.get('type', '')
    target_map = {'OHEX': 'OH*', 'CHEX': 'CH*', 'P': 'pressure', 'T': 'temperature'}
    target = target_map.get(target.upper(), target)
    return {'target': target, 'type': ig_type}


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
        entries.append((spec, val, kind))
    if not entries:
        return None
    target_kind, resolved = _reconcile_composition(entries)
    comp = {'kind': target_kind, 'species': []}
    for spec, val in resolved:
        spec['amount'] = [val]
        comp['species'].append(spec)
    return comp


def build_initial_composition(prop_defs, dp_elem):
    """Build initial composition dict from 'initial composition' columns."""
    entries = []
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
    if not entries:
        return None
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
        for extra_dg in all_dgs[1:]:
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
            if histories[0]['values']:
                datapoints[0].setdefault('time-histories', []).extend(histories)

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
        measured = build_composition(dg_defs, dp_el)
        if measured:
            dp['measured-composition'] = measured
        init_comp = build_initial_composition(dg_defs, dp_el)
        if init_comp:
            dp['composition'] = init_comp
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
        measured = build_composition(dg_defs, dp_el)
        if measured:
            dp['measured-composition'] = measured
        init_comp = build_initial_composition(dg_defs, dp_el)
        if init_comp:
            dp['composition'] = init_comp
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


def convert_file(xml_path):
    """Convert a single ReSpecTh XML file → ChemKED property dict (or None).

    Supports <experiment>, <kdetermination>, and <tdetermination> root elements.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    if root.tag == 'experiment':
        try:
            return _convert_file_inner(root, xml_path)
        except UnsupportedUnitsError as e:
            log.info(f'Skipping {os.path.basename(xml_path)}: {e}')
            return None
    elif root.tag == 'kdetermination':
        return _convert_kdetermination(root, xml_path)
    elif root.tag == 'tdetermination':
        return _convert_tdetermination(root, xml_path)
    else:
        return None


def _convert_file_inner(root, xml_path):

    xml_filename = os.path.basename(xml_path)

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

    return props


# ---------------------------------------------------------------------------
# kdetermination conversion
# ---------------------------------------------------------------------------

def _convert_kdetermination(root, xml_path):
    """Convert a <kdetermination> XML file to a ChemKED-style property dict."""
    xml_filename = os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)
    props['file-type'] = 'kdetermination'
    props['experiment-type'] = 'rate coefficient'

    # Parse reactions
    reactions = parse_reactions(root)
    if reactions:
        props['reactions'] = reactions

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

    return props


# ---------------------------------------------------------------------------
# tdetermination conversion
# ---------------------------------------------------------------------------

def _convert_tdetermination(root, xml_path):
    """Convert a <tdetermination> XML file to a ChemKED-style property dict."""
    xml_filename = os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)
    props['file-type'] = 'tdetermination'
    props['experiment-type'] = 'thermochemical'

    # Parse reactions (tdetermination may have species/reaction info)
    reactions = parse_reactions(root)
    if reactions:
        props['reactions'] = reactions

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
    stats = {'total': 0, 'success': 0, 'skipped': 0, 'errors': 0}
    errors_log = []
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
            else:
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, 'w') as f:
                    yaml_dump(result, f)

            stats['success'] += 1

        except Exception as e:
            stats['errors'] += 1
            errors_log.append((xml_str, str(e)))
            log.warning(f'Error converting {xml_path.name}: {e}')

    # Summary
    log.info('')
    log.info('=== Conversion Summary ===')
    log.info(f'Total files:  {stats["total"]}')
    log.info(f'Converted:    {stats["success"]}')
    log.info(f'Skipped:      {stats["skipped"]}')
    log.info(f'Errors:       {stats["errors"]}')
    log.info('')
    log.info('By experiment type:')
    for t, c in sorted(type_counts.items()):
        log.info(f'  {t}: {c}')

    if errors_log:
        log.info('')
        log.info(f'First 20 errors:')
        for path, err in errors_log[:20]:
            log.info(f'  {os.path.basename(path)}: {err}')

    return stats, errors_log


def convert_single(xml_path, output_path=None):
    """Convert a single file and optionally write output."""
    result = convert_file(xml_path)
    if result is None:
        log.info(f'Skipped (unsupported root element): {xml_path}')
        return

    if output_path is None:
        output_path = Path(xml_path).stem + '.yaml'

    with open(output_path, 'w') as f:
        yaml_dump(result, f)
    file_type = result.get('file-type', 'experiment')
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
