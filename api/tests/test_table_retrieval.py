"""Regression tests for rescuing relevant numeric tables without relaxing grounding."""

from dataclasses import replace

import pytest

from app.config import Settings
from app.retrieval.chroma import ChromaRetriever
from app.retrieval.tables import matches

from .test_retrieval import META, FakeClient, FakeCollection, FixedEmbedder, _row

QUESTION = 'How many faculty members did the Islamabad campus have according to the 2023-24 annual report?'
TABLE = 'Faculty Summary\nCampus | Professor | Lecturer | Total\nIslamabad | 19 | 83 | 236'


@pytest.mark.parametrize(('question', 'text', 'section', 'version', 'expected'), [
    (QUESTION, TABLE, 'Faculty Summary', '2023-24', True),
    (QUESTION.lower(), TABLE, 'Faculty Summary', '2023-24', True),
    (QUESTION, TABLE, 'Faculty Summary', '2019-20', False),
    (QUESTION, TABLE, 'Faculty Summary', '2023-25', False),
    (QUESTION, TABLE, 'Faculty Summary', '2023-2024', True),
    (QUESTION, TABLE, 'Graduation Summary', '2023-24', False),
    (QUESTION, 'Islamabad | excellent | faculty', 'Faculty Summary', '2023-24', False),
    ('How many hostel rooms are in Islamabad?', TABLE, 'Faculty Summary', '2023-24', False),
    ('Tell me about Islamabad faculty', TABLE, 'Faculty Summary', '2023-24', False),
])
def test_numeric_table_requires_matching_subject_row_and_edition(question, text, section, version, expected):
    assert matches(question, text, section, version, f'annual-report-{version}.pdf') is expected


class TableCollection(FakeCollection):
    def __init__(self, rows, table_embedding):
        super().__init__('rahbar-gg7', META, rows)
        self.table_embedding = table_embedding
        self.table_reads = 0

    def get(self, ids=None, where_document=None, include=None):
        if ids is not None:
            return {'ids': ids, 'embeddings': [self.table_embedding for _ in ids]}
        self.table_reads += 1
        rows = [r for r in self.rows if '|' in r['text']]
        return {'ids': [r['id'] for r in rows], 'documents': [r['text'] for r in rows],
                'metadatas': [r['meta'] for r in rows]}


def make_retriever(embedding, superseded=False):
    table = _row(3, 0.8, superseded=superseded, text=TABLE, section='Faculty Summary')
    table['meta'].update(source='annual-report-2023-24.pdf', doc_version='2023-24')
    rows = [_row(1, 0.1), _row(2, 0.2), table]
    col = TableCollection(rows, embedding)
    registry = FakeCollection('rahbar-registry', {'active': 'rahbar-gg7'}, [])
    retriever = ChromaRetriever(Settings(retriever='chroma', embed_model='nomic-embed-text',
                                        relevance_floor=0.6),
                                client=FakeClient([col, registry]), embedder=FixedEmbedder())
    return retriever, col


def test_table_rescue_keeps_real_cosine_and_caches_table_index():
    retriever, col = make_retriever([0.1, 0.1, 0.1])
    result = retriever.retrieve(QUESTION, 2)
    assert [p.chunk_id for p in result] == ['c3', 'c1']
    assert result[0].score == pytest.approx(1.0)
    retriever.retrieve(QUESTION, 2)
    assert col.table_reads == 1


def test_table_rescue_never_bypasses_relevance_floor_or_superseded_filter():
    low, _ = make_retriever([1.0, -1.0, 0.0])
    assert [p.chunk_id for p in low.retrieve(QUESTION, 2)] == ['c1', 'c2']
    old, _ = make_retriever([0.1, 0.1, 0.1], superseded=True)
    assert [p.chunk_id for p in old.retrieve(QUESTION, 2)] == ['c1', 'c2']


def test_unrelated_quantity_does_not_promote_the_table():
    retriever, _ = make_retriever([0.1, 0.1, 0.1])
    result = retriever.retrieve('How many hostel rooms are in Islamabad?', 2)
    assert [p.chunk_id for p in result] == ['c1', 'c2']


def test_reindex_refreshes_the_table_cache(monkeypatch):
    from app.retrieval import chroma

    retriever, original = make_retriever([0.1, 0.1, 0.1])
    assert retriever.retrieve(QUESTION, 2)[0].chunk_id == 'c3'
    replacement = TableCollection([_row(4, 0.1)], [0.1, 0.1, 0.1])
    replacement.name = 'rahbar-gg8'
    replacement.metadata = {**META, 'generation': 'g8'}
    retriever._client.collections[replacement.name] = replacement
    retriever._client.collections['rahbar-registry'].metadata = {'active': replacement.name}
    monkeypatch.setattr(chroma, 'POINTER_TTL', 0.0)
    assert [p.chunk_id for p in retriever.retrieve(QUESTION, 2)] == ['c4']
    assert original.table_reads == 1 and replacement.table_reads == 1


def test_table_index_failure_leaves_dense_retrieval_available(monkeypatch):
    retriever, col = make_retriever([0.1, 0.1, 0.1])

    def unavailable(**kwargs):
        raise ConnectionError('table index unavailable')

    monkeypatch.setattr(col, 'get', unavailable)
    assert [p.chunk_id for p in retriever.retrieve(QUESTION, 2)] == ['c1', 'c2']


def test_table_assist_respects_exact_assist_switch_and_clause_priority():
    retriever, col = make_retriever([0.1, 0.1, 0.1])
    retriever.settings = replace(retriever.settings, exact_term_assist=False)
    assert [p.chunk_id for p in retriever.retrieve(QUESTION, 2)] == ['c1', 'c2']
    assert col.table_reads == 0
    retriever.settings = replace(retriever.settings, exact_term_assist=True)
    retriever.retrieve(QUESTION + ' Under clause 1.21?', 2)
    assert col.table_reads == 0
