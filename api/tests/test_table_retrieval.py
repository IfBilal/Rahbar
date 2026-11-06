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

    def get(self, ids=None, where=None, where_document=None, include=None):
        if ids is not None:
            return {'ids': ids, 'embeddings': [self.table_embedding for _ in ids]}
        self.table_reads += 1
        rows = [r for r in self.rows if '|' in r['text']
                and (where is None or r['meta']['superseded'] is False)]
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


def test_explicit_history_can_match_a_superseded_table():
    retriever, _ = make_retriever([0.1, 0.1, 0.1], superseded=True)
    result = retriever.retrieve('Under the older report, ' + QUESTION, 2)
    assert result[0].chunk_id == 'c3' and result[0].superseded


def test_generated_numeric_answer_must_cite_the_matching_table():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE, source='annual-report-2023-24.pdf',
                    section='Faculty Summary', page=13, doc_version='2023-24', score=0.68)
    other = Passage(chunk_id='other', text='Islamabad campus description', source='other.pdf',
                    section='Campus', page=1, doc_version='2023-24', score=0.8)
    wrong = grounded(other).model_copy(update={'answer': '236 [B]'})
    right = grounded(table).model_copy(update={'answer': '236 [A]'})
    provider = ScriptedProvider(wrong, right)
    answer, reason, attempts = generate_checked(QUESTION, [table, other], provider)
    assert reason is None and attempts == 2
    assert answer is not None and answer.citations[0].section == 'Faculty Summary'
    assert 'numeric table' in provider.calls[1]


def test_repeated_wrong_table_citation_falls_back():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE, source='annual-report-2023-24.pdf',
                    section='Faculty Summary', page=13, doc_version='2023-24', score=0.68)
    other = Passage(chunk_id='other', text='Islamabad campus description', source='other.pdf',
                    section='Campus', page=1, doc_version='2023-24', score=0.8)
    wrong = grounded(other).model_copy(update={'answer': '236 [B]'})
    answer, reason, attempts = generate_checked(QUESTION, [table, other],
                                                ScriptedProvider(wrong, wrong))
    assert answer is None and attempts == 2 and reason and 'numeric table' in reason


def test_table_in_citation_list_cannot_hide_an_unrelated_inline_citation():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE, source='annual-report-2023-24.pdf',
                    section='Faculty Summary', page=13, doc_version='2023-24', score=0.68)
    other = Passage(chunk_id='other', text='Islamabad campus description', source='other.pdf',
                    section='Campus', page=1, doc_version='2023-24', score=0.8)
    wrong = grounded(table).model_copy(update={'answer': '236 [B]'})
    right = grounded(table).model_copy(update={'answer': '236 [A]'})
    answer, reason, attempts = generate_checked(QUESTION, [table, other],
                                               ScriptedProvider(wrong, right))
    assert reason is None and attempts == 2
    assert answer is not None and '[annual-report-2023-24.pdf / Faculty Summary]' in answer.answer


def test_wrong_numeric_row_is_retried_even_if_the_table_is_cited():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE + '\nTotal | 42 | 325 | 30 | 735',
                    source='annual-report-2023-24.pdf', section='Faculty Summary',
                    page=13, doc_version='2023-24', score=0.68)
    wrong = grounded(table).model_copy(update={'answer': 'In 2023-24, the count was 30 [A].'})
    right = grounded(table).model_copy(update={'answer': 'In 2023-24, the count was 236 [A].'})
    provider = ScriptedProvider(wrong, right)
    answer, reason, attempts = generate_checked(QUESTION, [table], provider)
    assert reason is None and attempts == 2
    assert answer is not None and '236' in answer.answer
    assert 'row naming the entity' in provider.calls[1]


def test_repeated_wrong_numeric_row_falls_back():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE + '\nTotal | 42 | 325 | 30 | 735',
                    source='annual-report-2023-24.pdf', section='Faculty Summary',
                    page=13, doc_version='2023-24', score=0.68)
    wrong = grounded(table).model_copy(update={'answer': 'The count was 30 [A].'})
    answer, reason, attempts = generate_checked(QUESTION, [table], ScriptedProvider(wrong, wrong))
    assert answer is None and attempts == 2 and reason and 'row naming the entity' in reason


def test_prompt_highlights_the_matching_row_as_untrusted_evidence():
    from app.schemas import Passage
    from app.services.prompt import build_messages

    table = Passage(chunk_id='table', text=TABLE + '\nTotal | 42 | 325 | 30 | 735',
                    source='annual-report-2023-24.pdf', section='Faculty Summary',
                    page=13, doc_version='2023-24', score=0.68)
    text = build_messages(QUESTION, [table])[1]['content']
    assert '<matched_row evidence="A">Islamabad | 19 | 83 | 236</matched_row>' in text
    assert '<matched_row evidence="A">Total' not in text
    assert 'untrusted excerpts' in text


def test_correct_row_value_followed_by_sentence_period_is_accepted():
    from app.schemas import Passage
    from app.services.answer import generate_checked
    from .fakes import ScriptedProvider, grounded

    table = Passage(chunk_id='table', text=TABLE, source='annual-report-2023-24.pdf',
                    section='Faculty Summary', page=13, doc_version='2023-24', score=0.68)
    correct = grounded(table).model_copy(update={'answer': 'The total was 236. [A]'})
    answer, reason, attempts = generate_checked(QUESTION, [table], ScriptedProvider(correct))
    assert answer is not None and reason is None and attempts == 1
