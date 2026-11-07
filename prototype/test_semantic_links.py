import copy
import unittest
from semantic_links import add_link, remove_link, undo_link

class LinkTests(unittest.TestCase):
    def graph(self):
        return {'nodes': [{'id': 'a', 'type': 'word', 'text': 'Haus'}, {'id': 'b', 'type': 'image', 'text': 'house', 'image_assets': ['asset-1']}],
                'edges': [{'from': 'a', 'to': 'b', 'relation': 'meaning', 'label': 'original'}]}

    def test_unlink_undo_preserves_gallery_and_later_text(self):
        doc = self.graph(); before = copy.deepcopy(doc)
        changed, token = remove_link(doc, 'a', 'b', 'meaning')
        self.assertEqual(doc, before)
        changed['nodes'][0]['text'] = 'later edit'
        restored = undo_link(changed, token)
        self.assertEqual(restored['nodes'][0]['text'], 'later edit')
        self.assertEqual(restored['nodes'][1]['image_assets'], ['asset-1'])
        self.assertEqual(restored['edges'], before['edges'])

    def test_idempotent_link_and_reversible_new_link(self):
        doc = self.graph()
        same, token = add_link(doc, 'a', 'b', 'meaning')
        self.assertEqual(undo_link(same, token), doc)
        changed, token = add_link(doc, 'b', 'a')
        self.assertEqual(undo_link(changed, token), doc)

    def test_conflicting_later_edge_edit_not_overwritten(self):
        changed, token = add_link(self.graph(), 'b', 'a')
        changed['edges'][-1]['label'] = 'later'
        with self.assertRaises(ValueError): undo_link(changed, token)

    def test_invalid_link_is_rejected(self):
        with self.assertRaises(ValueError): add_link(self.graph(), 'a', 'missing')
        with self.assertRaises(ValueError): add_link(self.graph(), 'a', 'b', 'unsupported')

if __name__ == '__main__': unittest.main()
