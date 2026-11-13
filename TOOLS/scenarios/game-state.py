"""Read-only layout binding for offline snapshot preparation and verification."""
import ctypes as C
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'TEST/HOST'))
from state import Game, Campaign, Battle

# Preserve Pascal array bounds and booleans; ctypes alone loses both. This is
# the single binding used by the semantic compiler, not another offset table.
declarations = {}
for filename in ('KBTYPES.PAS', 'KBSTATE.PAS', 'KBBTYPE.PAS'):
    source = (ROOT / 'SRC' / filename).read_bytes().decode('cp866')
    source = re.sub(r'\{.*?\}', '', source, flags=re.S)
    for name, body in re.findall(r'(\w+)\s*=\s*packed\s+record\b(.*?)\bend\s*;', source, re.I | re.S):
        entries = {}
        if name == 'TCreatureCost':
            continue
        for entry in body.split(';'):
            if ':' not in entry:
                continue
            names, kind = entry.split(':', 1)
            for field in names.split(','):
                entries[field.strip()] = kind.strip()
        declarations[name] = entries

def describe(kind, declaration=''):
    result = dict(size=C.sizeof(kind))
    if hasattr(kind, '_fields_'):
        result['kind'] = kind.__name__
        result['fields'] = {
            name: dict(offset=getattr(kind, name).offset,
                       **describe(field_type, declarations.get(kind.__name__, {}).get(name, '')))
            for name, field_type in kind._fields_ if not name.startswith('Unknown')}
    elif hasattr(kind, '_length_'):
        string = re.fullmatch(r'string\[(\d+)\]', declaration, re.I)
        if string:
            result.update(string=int(string[1]))
        else:
            match = re.fullmatch(r'array\[(.*?)\]\s+of\s+(.*)', declaration, re.I | re.S)
            bounds, child = (match[1].split(','), match[2]) if match else (['0..'+str(kind._length_-1)], '')
            lo, hi = map(int, bounds[0].split('..'))
            if len(bounds)>1:
                child = 'array['+','.join(bounds[1:])+'] of '+child
            result.update(lo=lo, hi=hi, item=describe(kind._type_, child))
    else:
        result.update(boolean=declaration.lower()=='boolean', signed=kind(-1).value<0)
    return result

tables = (ROOT / 'SRC/KBTABLES.PAS').read_bytes().decode('cp866')
block = tables[tables.index('CreatureDefinitions:'):tables.index('WorkerCapacities:')]
creatures = []
pattern = r"Name:\s*'([^']+)';\s*Cost:\s*\((.*?)\);\s*Movement:\s*(\d+);\s*Flags:\s*(\d+);\s*Defense:\s*(\d+);\s*Attack:\s*(\d+)"
for i, (name, cost, movement, flags, defense, attack) in enumerate(re.findall(pattern, block, re.S)):
    creatures.append(dict(id=i, name=name, movement=int(movement), flags=int(flags), defense=int(defense), attack=int(attack)))
assert len(creatures) == 30
catalogs = {}
for name in ('ScrollNames', 'SpellColors', 'SpellEffects', 'GoodsNames', 'Difficulties'):
    match = re.search(name+r':\s*array\[(\d+)\.\.(\d+)\].*?=\s*\((.*?)\);', tables, re.S | re.I)
    if match:
        catalogs[name] = [dict(id=int(match[1])+i, name=text) for i, text in enumerate(re.findall(r"'([^']*)'", match[3]))]

fields = {}
def walk(kind, prefix='', offset=0):
    for name, field_type in kind._fields_:
        key = prefix + name
        at = offset + getattr(kind, name).offset
        fields[key] = dict(offset=at, size=C.sizeof(field_type))
        if hasattr(field_type, '_fields_'):
            walk(field_type, key + '.', at)
walk(Game)
exe = Path(sys.argv[1]).read_bytes()
save = list(re.finditer(rb'\x8d\x36(..)\x8d\x3e(..)\x83\xc7\x10', exe, re.S))
random = list(re.finditer(rb'\xa1(..)\x8b\x1e(..)\x8b\xc8\x2e\xf7\x26', exe, re.S))
if len(save) != 1 or len(random) != 1:
    raise ValueError('Cannot bind offline inspector to this executable')
game_offset = struct.unpack('<H', save[0][1])[0] - Game.Campaign.offset
seed_offset, high_offset = struct.unpack('<HH', random[0][1] + random[0][2])
assert high_offset == seed_offset + 2
print(json.dumps(dict(gameSize=C.sizeof(Game), gameDataOffset=game_offset,
                     seedDelta=seed_offset-game_offset, fields=fields,
                     campaign=describe(Campaign), battle=describe(Battle),
                     runtime=describe(Game._fields_[0][1]), world=describe(Game._fields_[2][1]),
                     creatures=creatures, catalogs=catalogs)))
