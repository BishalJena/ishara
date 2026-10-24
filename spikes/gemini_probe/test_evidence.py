"""The committed source list names only sources that reached the probe, once each."""
import unittest

import evidence


def source(ident, dataset, url):
    return {"source_id": ident, "dataset": dataset, "url": url, "terms": f"{dataset} terms"}


class SourcesList(unittest.TestCase):
    def test_only_used_sources_grouped_by_dataset_with_unique_urls(self):
        spec = {"sources": [source("a", "include", "https://zenodo/x"), source("b", "include", "https://zenodo/x"),
                            source("c", "islrtc", "https://hf/c"), source("d", "youtube", "https://yt/d")]}
        listed = evidence.sources_list(spec, used={"a", "b", "c"})
        self.assertEqual(set(listed), {"include", "islrtc"})
        self.assertEqual(listed["include"], {"role": "test", "terms": "include terms", "urls": ["https://zenodo/x"],
                                             "count": 1})
        self.assertEqual(listed["islrtc"]["role"], "reference")


if __name__ == "__main__":
    unittest.main()
