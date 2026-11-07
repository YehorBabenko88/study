"""Pure semantic scene planning. No I/O, image generation, or asset deletion.

Board-compatible typed nodes/edges become deterministic descriptive prompts.
Image provenance records available assets, never evidence of model conditioning.
"""
from collections import deque
from copy import deepcopy
from html import unescape
import re
import unicodedata
from typing import Literal, TypedDict

NodeType = Literal['letter', 'word', 'syllable', 'image', 'sentence', 'note', 'action']
Relation = Literal['association', 'part_of', 'sequence', 'meaning', 'sound', 'action']
NODE_TYPES = {'letter', 'word', 'syllable', 'image', 'sentence', 'note', 'action'}
RELATIONS = {'association', 'part_of', 'sequence', 'meaning', 'sound', 'action'}


class SemanticNode(TypedDict, total=False):
    id: str
    type: NodeType
    text: str
    asset_id: str
    scene_id: str
    image_assets: list[str]


SemanticEdge = TypedDict('SemanticEdge', {'from': str, 'to': str, 'relation': Relation})


def _clean(value, limit=240):
    value = re.sub(r'<[^>]*>', '', unescape(value))
    value = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in value)
    return ' '.join(value.split())[:limit]


def _graph(document):
    if not isinstance(document, dict):
        raise ValueError('document must be an object')
    nodes, edges = document.get('nodes', []), document.get('edges', [])
    if not isinstance(nodes, list) or len(nodes) > 10000 or not isinstance(edges, list) or len(edges) > 30000:
        raise ValueError('graph exceeds limits')
    indexed = {}
    for node in nodes:
        if not isinstance(node, dict): raise ValueError('invalid node')
        nid = node.get('id')
        if not isinstance(nid, str) or not nid or len(nid) > 80 or nid in indexed:
            raise ValueError('invalid or duplicate node id')
        if node.get('type') not in NODE_TYPES: raise ValueError('invalid node type')
        if not isinstance(node.get('text', ''), str) or len(node.get('text', '')) > 5000:
            raise ValueError('invalid node text')
        for key in ('asset_id', 'scene_id'):
            if key in node and (not isinstance(node[key], str) or len(node[key]) > 200):
                raise ValueError('invalid provenance')
        assets = node.get('image_assets', [])
        if not isinstance(assets, list) or len(assets) > 12 or any(not isinstance(x, str) or len(x) > 200 for x in assets):
            raise ValueError('invalid image gallery')
        indexed[nid] = node
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get('from'), str) or not isinstance(edge.get('to'), str) or edge.get('from') not in indexed or edge.get('to') not in indexed:
            raise ValueError('dangling edge')
        if edge.get('relation', 'association') not in RELATIONS: raise ValueError('invalid relation')
    return indexed, edges


def compose(document, root_id, *, max_depth=3, max_nodes=64, max_prompt_chars=1200, use_references=False):
    """Traverse incident links breadth-first with stable ordering and bounded output.

    References are deliberately unavailable until an image-conditioned executor is
    implemented. Supplying image assets alone never switches generation mode.
    """
    if use_references: raise ValueError('image-conditioned workflow is not supported by this composer')
    for value, minimum, maximum in ((max_depth, 0, 32), (max_nodes, 1, 256), (max_prompt_chars, 1, 1200)):
        if type(value) is not int or not minimum <= value <= maximum: raise ValueError('invalid traversal limit')
    nodes, edges = _graph(document)
    if not isinstance(root_id, str) or root_id not in nodes: raise ValueError('unknown root node')
    neighbors = {nid: set() for nid in nodes}
    for edge in edges:
        neighbors[edge['from']].add(edge['to']); neighbors[edge['to']].add(edge['from'])
    queue = deque([(root_id, 0)]); seen = {root_id}; selected = []
    while queue and len(selected) < max_nodes:
        nid, depth = queue.popleft(); selected.append(nid)
        if depth < max_depth:
            for other in sorted(neighbors[nid]):
                if other not in seen and len(seen) < max_nodes:
                    seen.add(other); queue.append((other, depth + 1))
    selected.sort(); included = set(selected)
    lines = ['Compose one coherent visual scene from these concepts:']
    provenance = []
    for nid in selected:
        node = nodes[nid]; lines.append(f"{node['type']}: {_clean(node.get('text', ''))}")
        assets = sorted(set(node.get('image_assets', []) + ([node['asset_id']] if node.get('asset_id') else [])))
        provenance.append({'node_id': nid, 'node_type': node['type'], 'asset_ids': assets, 'scene_id': node.get('scene_id')})
    relations = sorted(set((e['from'], e.get('relation', 'association'), e['to']) for e in edges if e['from'] in included and e['to'] in included))
    # Use sanitized concept labels, never raw ids as prompt content.
    for source, relation, target in relations:
        lines.append(f"{_clean(nodes[source].get('text', ''))} {relation} {_clean(nodes[target].get('text', ''))}")
    prompt = '\n'.join(lines)
    return {'prompt': prompt[:max_prompt_chars], 'prompt_truncated': len(prompt) > max_prompt_chars, 'node_ids': selected, 'provenance': provenance,
            'generation_mode': 'text-to-image', 'reference_images_used': False}


def _key(edge):
    return edge['from'], edge['to'], edge.get('relation', 'association')


def _edit(document, source, target, relation, remove):
    nodes, edges = _graph(document)
    if source not in nodes or target not in nodes or relation not in RELATIONS: raise ValueError('invalid link')
    key = (source, target, relation)
    matches = [(i, deepcopy(e)) for i, e in enumerate(edges) if _key(e) == key]
    result = deepcopy(document); result.setdefault('edges', [])
    token = {'operation': 'none', 'key': key}
    if remove and matches:
        result['edges'] = [e for e in result['edges'] if _key(e) != key]
        token = {'operation': 'restore', 'key': key, 'edges': matches}
    elif not remove and not matches:
        edge = {'from': source, 'to': target, 'relation': relation}
        result['edges'].append(edge)
        token = {'operation': 'remove', 'key': key, 'edge': deepcopy(edge)}
    return result, token


def add_link(document, source, target, relation='association'):
    return _edit(document, source, target, relation, False)


def remove_link(document, source, target, relation='association'):
    return _edit(document, source, target, relation, True)


def undo_link(document, token):
    """Undo only the link edit, preserving later node/gallery changes.

    A conflicting subsequent edge edit raises instead of overwriting that edit.
    Tokens are local edit results, not an untrusted persistence interchange format.
    """
    _, edges = _graph(document); result = deepcopy(document); result.setdefault('edges', [])
    matches = [e for e in edges if _key(e) == tuple(token['key'])]
    if token['operation'] == 'remove':
        if matches != [token['edge']]: raise ValueError('link changed since edit')
        result['edges'] = [e for e in result['edges'] if _key(e) != tuple(token['key'])]
    elif token['operation'] == 'restore':
        if matches: raise ValueError('link changed since edit')
        for index, edge in token['edges']: result['edges'].insert(index, deepcopy(edge))
    elif token['operation'] != 'none': raise ValueError('invalid undo operation')
    _graph(result)
    return result

