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


def yaml_dump(data, stream):
    """Dump data to YAML preserving dict key order."""
    yaml.dump(data, stream, Dumper=_OrderedDumper,
              default_flow_style=False, allow_unicode=True)

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
    """Convert ReSpecTh property name → ChemKED YAML key."""
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
    return {
        'file-authors': [{'name': file_author or 'Unknown'}],
        'file-version': 0,
        'chemked-version': CHEMKED_VERSION,
    }


def parse_reference(root, xml_filename):
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
                ref['volume'] = int(vol)
            except ValueError:
                ref['volume'] = vol
        pages = (details.findtext('pages') or '').strip()
        if pages:
            ref['pages'] = pages

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


def _build_inline_uncertainty(kind, bound, value_str, units):
    """Build a PyKED inline uncertainty dict from ReSpecTh attributes.

    Maps:
      kind='absolute'|'relative' → uncertainty-type
      bound='plusminus'          → uncertainty: <value>
      bound='plus'               → upper-uncertainty: <value>
      bound='minus'              → lower-uncertainty: <value>
    """
    unc_dict = {'uncertainty-type': kind}
    if kind == 'absolute':
        unc_value = f'{value_str} {units}'.strip()
    else:
        # relative uncertainties are unitless
        unc_value = value_str
    if bound in ('plusminus', ''):
        unc_dict['uncertainty'] = unc_value
    elif bound == 'plus':
        unc_dict['upper-uncertainty'] = unc_value
    elif bound == 'minus':
        unc_dict['lower-uncertainty'] = unc_value
    else:
        unc_dict['uncertainty'] = unc_value
    return unc_dict


def _merge_inline_uncertainty(existing, new):
    """Merge two inline uncertainty dicts (e.g. separate plus + minus → one dict)."""
    merged = dict(existing)
    for key in ('uncertainty', 'upper-uncertainty', 'lower-uncertainty'):
        if key in new:
            merged[key] = new[key]
    return merged


def _attach_comp_uncertainty_inline(comp_block, species_name, kind, bound,
                                    raw_value, units):
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
                entry['value'] = [f'{_clean_numeric(val_el.text)} {units}']
            entries.append(entry)
    else:
        val_el = prop_elem.find('value')
        if val_el is not None:
            entry = dict(base)
            entry['value'] = [f'{_clean_numeric(val_el.text)} {units}']
            entries.append(entry)
    return entries


def parse_common_properties(root, exp_type):
    common = {}
    pending_uncs = []  # uncertainty prop_elems to process in second pass

    # First pass: collect scalar properties, compositions, eval-std-dev
    for prop_elem in root.findall('commonProperties/property'):
        name = prop_elem.attrib.get('name', '')

        if name == 'initial composition':
            common['composition'] = parse_initial_composition(prop_elem)
        elif name == 'equivalence ratio':
            val_el = prop_elem.find('value')
            if val_el is not None:
                common['equivalence-ratio'] = float(val_el.text)
        elif name in SCALAR_COMMON_PROPS:
            val_el = prop_elem.find('value')
            units = prop_elem.attrib.get('units', '')
            if val_el is not None:
                key = prop_name_to_key(name)
                common[key] = [f'{_clean_numeric(val_el.text)} {units}']
        elif name == 'uncertainty':
            pending_uncs.append(prop_elem)
        elif name == 'evaluated standard deviation':
            entries = _parse_esd_common(prop_elem)
            if entries:
                common.setdefault('evaluated-standard-deviation', []).extend(entries)

    # Second pass: attach uncertainty inline or as standalone list
    inline_uncs = {}  # key → inline unc dict (for merging plus/minus pairs)
    for prop_elem in pending_uncs:
        attrs = prop_elem.attrib
        reference = attrs.get('reference', '')
        kind = attrs.get('kind', '')
        units = attrs.get('units', '')
        bound = attrs.get('bound', '')

        target_key = _ref_to_property_key(reference)
        if target_key is not None and target_key in common:
            # Scalar-reference: convert to inline uncertainty on the property
            val_el = prop_elem.find('value')
            if val_el is not None:
                unc_dict = _build_inline_uncertainty(
                    kind, bound, _clean_numeric(val_el.text), units
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
                    raw_val, units
                ):
                    # Species not found in composition – fall back to standalone
                    entry = {'reference': reference, 'kind': kind}
                    for attr in ('sourcetype', 'bound'):
                        v = attrs.get(attr)
                        if v:
                            entry[attr] = v
                    entry.update(spec)
                    if units in ('ppm', 'ppb', 'percent'):
                        conv_val, conv_units = normalize_comp_units(
                            val_el.text.strip(), units
                        )
                        entry['value'] = [f'{conv_val} {conv_units}']
                    else:
                        entry['value'] = [f'{raw_val} {units}']
                    common.setdefault('uncertainty', []).append(entry)
        else:
            # Unresolved reference: standalone list
            base = {'reference': reference, 'kind': kind}
            for attr in ('sourcetype', 'bound'):
                val = attrs.get(attr)
                if val:
                    base[attr] = val
            val_el = prop_elem.find('value')
            if val_el is not None:
                entry = dict(base)
                entry['value'] = [f'{_clean_numeric(val_el.text)} {units}']
                common.setdefault('uncertainty', []).append(entry)

    # Attach inline uncertainties to their property fields
    for key, unc_dict in inline_uncs.items():
        prop_val = common[key]
        if isinstance(prop_val, list) and len(prop_val) >= 1:
            # Append inline uncertainty dict: ['1010 K'] → ['1010 K', {...}]
            common[key] = [prop_val[0], unc_dict]

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
    """Build uncertainty and evaluated-standard-deviation entries from datapoint columns.

    For uncertainty entries:
      - Scalar references (temperature, pressure, etc.) are converted to inline
        PyKED uncertainty format and attached directly to dp[key] if dp is given.
      - Composition references are inlined on the matching species ``amount``
        field in dp['composition'] or dp['measured-composition'] when possible.

    For eval-std-dev, all entries stay as standalone list entries.

    Returns (standalone_unc_entries, esd_entries).
    """
    standalone_unc = []
    esd_entries = []
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
            entry = {'reference': ref, 'kind': kind}
            for attr in ('sourcetype', 'method'):
                if attr in pdef:
                    entry[attr] = pdef[attr]
            if 'species' in pdef:
                entry.update(pdef['species'])
            if ref in ('composition', 'initial composition') and units in ('ppm', 'ppb', 'percent'):
                conv_val, conv_units = normalize_comp_units(val_el.text.strip(), units)
                entry['value'] = [f'{conv_val} {conv_units}']
            else:
                entry['value'] = [f'{_clean_numeric(val_el.text)} {units}']
            esd_entries.append(entry)
            continue

        # name == 'uncertainty'
        target_key = _ref_to_property_key(ref, dg_defs)
        if target_key is not None and dp is not None and target_key in dp:
            # Scalar reference: build inline uncertainty
            bound = pdef.get('bound', '')
            unc_dict = _build_inline_uncertainty(
                kind, bound, _clean_numeric(val_el.text), units
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
                        comp_block, species_name, kind, bound, raw_val, units
                    ):
                        inlined = True
                        break
            if not inlined:
                # Fall back to standalone
                entry = {'reference': ref, 'kind': kind}
                for attr in ('sourcetype', 'bound'):
                    if attr in pdef:
                        entry[attr] = pdef[attr]
                if 'species' in pdef:
                    entry.update(pdef['species'])
                if units in ('ppm', 'ppb', 'percent'):
                    conv_val, conv_units = normalize_comp_units(val_el.text.strip(), units)
                    entry['value'] = [f'{conv_val} {conv_units}']
                else:
                    entry['value'] = [f'{raw_val} {units}']
                standalone_unc.append(entry)
        else:
            # Unresolved reference: standalone
            entry = {'reference': ref, 'kind': kind}
            for attr in ('sourcetype', 'bound'):
                if attr in pdef:
                    entry[attr] = pdef[attr]
            if 'species' in pdef:
                entry.update(pdef['species'])
            if ref in ('composition', 'initial composition') and units in ('ppm', 'ppb', 'percent'):
                conv_val, conv_units = normalize_comp_units(val_el.text.strip(), units)
                entry['value'] = [f'{conv_val} {conv_units}']
            else:
                entry['value'] = [f'{_clean_numeric(val_el.text)} {units}']
            standalone_unc.append(entry)

    # Attach inline uncertainties to the datapoint property fields
    if dp is not None:
        for key, unc_dict in inline_uncs.items():
            prop_val = dp[key]
            if isinstance(prop_val, list) and len(prop_val) >= 1:
                dp[key] = [prop_val[0], unc_dict]

    return standalone_unc, esd_entries


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
        unc, esd = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        if esd:
            dp['evaluated-standard-deviation'] = esd
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
                            h['values'].append([t_val, q_vals[h['type']]])
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
                dp['equivalence-ratio'] = float(val_el.text)
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc, esd = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        if esd:
            dp['evaluated-standard-deviation'] = esd
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
        unc, esd = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        if esd:
            dp['evaluated-standard-deviation'] = esd
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
            profile['values'].append([t_val, c_val])
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
                dp['equivalence-ratio'] = float(val_el.text)
            elif name in SCALAR_DG_PROPS:
                dp[prop_name_to_key(name)] = _scalar_value(val_el.text, pdef['units'])
        unc, esd = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        if esd:
            dp['evaluated-standard-deviation'] = esd
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
        unc, esd = build_uncertainty_entries(dg_defs, dp_el, dp)
        if unc:
            dp['uncertainty'] = unc
        if esd:
            dp['evaluated-standard-deviation'] = esd
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
    """Convert a single ReSpecTh XML file → ChemKED property dict (or None)."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Only handle <experiment> root elements
    if root.tag != 'experiment':
        return None

    # Skip files with unsupported composition units (e.g. mol/cm3)
    try:
        return _convert_file_inner(root, xml_path)
    except UnsupportedUnitsError as e:
        log.info(f'Skipping {os.path.basename(xml_path)}: {e}')
        return None


def _convert_file_inner(root, xml_path):

    xml_filename = os.path.basename(xml_path)

    props = parse_file_metadata(root)
    props['reference'] = parse_reference(root, xml_filename)

    exp_type, apparatus = parse_experiment_kind(root)
    props['experiment-type'] = exp_type
    props['apparatus'] = apparatus

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
    for dp in props['datapoints']:
        remaining = []
        for entry in dp.get('uncertainty', []):
            ref = entry.get('reference', '')
            target_key = _ref_to_property_key(ref)
            if target_key and target_key in dp:
                unc_kind = entry.get('kind', '')
                bound = entry.get('bound', '')
                val_parts = entry.get('value', [''])[0].split(' ', 1)
                val_str = val_parts[0]
                unc_units = val_parts[1] if len(val_parts) > 1 else ''
                unc_dict = _build_inline_uncertainty(unc_kind, bound, val_str, unc_units)
                prop_val = dp[target_key]
                if isinstance(prop_val, list) and len(prop_val) >= 1:
                    if len(prop_val) == 2 and isinstance(prop_val[1], dict):
                        dp[target_key] = [prop_val[0], _merge_inline_uncertainty(prop_val[1], unc_dict)]
                    else:
                        dp[target_key] = [prop_val[0], unc_dict]
                else:
                    remaining.append(entry)
            elif ref in ('composition', 'initial composition'):
                species_name = entry.get('species-name', '')
                unc_kind = entry.get('kind', '')
                bound = entry.get('bound', '')
                val_parts = entry.get('value', [''])[0].split(' ', 1)
                val_str = val_parts[0]
                unc_units = val_parts[1] if len(val_parts) > 1 else ''
                inlined = False
                if species_name:
                    for comp_key in ('composition', 'measured-composition'):
                        comp_block = dp.get(comp_key)
                        if comp_block and _attach_comp_uncertainty_inline(
                            comp_block, species_name, unc_kind, bound,
                            val_str, unc_units
                        ):
                            inlined = True
                            break
                if not inlined:
                    remaining.append(entry)
            else:
                remaining.append(entry)
        if remaining:
            dp['uncertainty'] = remaining
        elif 'uncertainty' in dp:
            del dp['uncertainty']

    # Clean up common uncertainty list: keep only entries still referenced by
    # at least one datapoint (avoids duplication with inline values).
    if 'uncertainty' in common:
        # Gather keys of entries still needed by datapoints
        still_needed = set()
        for dp in props['datapoints']:
            for entry in dp.get('uncertainty', []):
                key = (entry.get('reference', ''), entry.get('species-name', ''),
                       entry.get('kind', ''), entry.get('bound', ''))
                still_needed.add(key)
        remaining_common = [
            e for e in common['uncertainty']
            if (e.get('reference', ''), e.get('species-name', ''),
                e.get('kind', ''), e.get('bound', '')) in still_needed
        ]
        if remaining_common:
            common['uncertainty'] = remaining_common
        else:
            del common['uncertainty']

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
        log.info(f'Skipped (not an <experiment> file): {xml_path}')
        return

    if output_path is None:
        output_path = Path(xml_path).stem + '.yaml'

    with open(output_path, 'w') as f:
        yaml_dump(result, f)
    log.info(f'Converted: {xml_path} → {output_path}')


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
