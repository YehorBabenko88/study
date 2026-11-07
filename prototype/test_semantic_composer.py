import copy
import unittest
from semantic_composer import compose, add_link, remove_link, undo_link


class ComposerTests(unittest.TestCase):
    def graph(self):
        return {'nodes': [
            {'id': 'b', 'type': 'image', 'text': '<b>forest</b>\x00\n', 'asset_id': 'asset-1', 'image_assets': ['asset-1', 'asset-2']},
            {'id': 'a', 'type': 'word', 'text': 'Haus'},
            {'id': 'c', 'type': 'action', 'text': 'stands'}],
            'edges': [{'from': 'a', 'to': 'b', 'relation': 'meaning'}, {'from': 'b', 'to': 'c', 'relation': 'action'}, {'from': 'c', 'to': 'a', 'relation': 'association'}]}

    def test_deterministic_and_does_not_mutate(self):
        doc = self.graph(); before = copy.deepcopy(doc)
        result = compose(doc, 'a')
        doc['nodes'].reverse(); doc['edges'].reverse()
        self.assertEqual(result, compose(doc, 'a'))
        self.assertEqual(before['nodes'], list(reversed(doc['nodes'])))
        self.assertIn('word: Haus', result['prompt'])
        self.assertIn('image: forest', result['prompt'])
        self.assertNotIn('<b>', result['prompt'])
        self.assertNotIn('\x00', result['prompt'])

    def test_bounds_and_cycles(self):
        self.assertEqual(compose(self.graph(), 'a', max_depth=0)['node_ids'], ['a'])
        self.assertEqual(len(compose(self.graph(), 'a', max_nodes=2)['node_ids']), 2)
        self.assertEqual(len(compose(self.graph(), 'a')['node_ids']), 3)
        for kwargs in ({'max_depth': -1}, {'max_nodes': 0}, {'max_nodes': 10001}, {'max_depth': True}):
            with self.assertRaises(ValueError): compose(self.graph(), 'a', **kwargs)

    def test_provenance_is_not_a_reference_claim(self):
        result = compose(self.graph(), 'a')
        self.assertEqual(result['generation_mode'], 'text-to-image')
        self.assertFalse(result['reference_images_used'])
        self.assertEqual(result['provenance'][1]['asset_ids'], ['asset-1', 'asset-2'])
        with self.assertRaises(ValueError): compose(self.graph(), 'a', use_references=True)

    def test_prompt_size_and_encoded_markup(self):
        doc = {'nodes': [{'id': str(i), 'type': 'note', 'text': '&lt;b&gt;' + 'x' * 400 + '&lt;/b&gt;'} for i in range(80)],
               'edges': [{'from': '0', 'to': str(i), 'relation': 'meaning'} for i in range(1, 80)]}
        result = compose(doc, '0', max_nodes=80)
        self.assertLessEqual(len(result['prompt']), 8192)
        self.assertTrue(result['prompt_truncated'])
        self.assertNotIn('<b>', result['prompt'])

    def test_invalid_graph(self):
        for doc in ({'nodes': [], 'edges': []}, {'nodes': [{'id': 'a', 'type': 'script'}]}, {'nodes': [{'id': 'a', 'type': 'word'}], 'edges': [{'from': 'a', 'to': 'missing'}]}):
            with self.assertRaises(ValueError): compose(doc, 'a')

    def test_non_destructive_links_and_undo(self):
        doc = self.graph(); before = copy.deepcopy(doc)
        updated, token = remove_link(doc, 'a', 'b', 'meaning')
        self.assertEqual(doc, before)
        updated['nodes'][0]['text'] = 'edited after unlink'
        restored = undo_link(updated, token)
        self.assertEqual(restored['nodes'][0]['text'], 'edited after unlink')
        self.assertEqual(restored['nodes'][0]['image_assets'], ['asset-1', 'asset-2'])
        self.assertEqual(restored['edges'], before['edges'])
        linked, token = add_link(doc, 'a', 'c', 'sequence')
        self.assertEqual(undo_link(linked, token), doc)
        # Duplicate links are idempotent; undo must not remove an original link.
        same, token = add_link(doc, 'a', 'b', 'meaning')
        self.assertEqual(undo_link(same, token), doc)

    def test_undo_does_not_overwrite_new_edge_metadata(self):
        doc, token = add_link(self.graph(), 'a', 'c', 'sequence')
        doc['edges'][-1]['label'] = 'new edit'
        with self.assertRaises(ValueError): undo_link(doc, token)

if __name__ == '__main__': unittest.main()
