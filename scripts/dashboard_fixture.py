"""Generate labeled dashboard test data; never execute candidate code."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from branchforge.models import Candidate, EvaluationResult, SearchTree


def generate(root: Path = Path('runs'), count: int = 500) -> None:
    directory = root / 'synthetic-dashboard'
    directory.mkdir(parents=True, exist_ok=True)
    tree = SearchTree()
    events = []
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def emit(kind: str, **data: object) -> None:
        events.append(dict(schema_version=2, run_id=directory.name, sequence=len(events)+1,
            event_type=kind, timestamp=(start+timedelta(milliseconds=len(events)*10)).isoformat(), **data))

    emit('RUN_STARTED', root=tree.nodes['root'].model_dump(mode='json'), algorithm='beam')
    for batch in range(0, count, 8):
        for i in range(batch, min(batch+8, count)):
            emit('BRANCH_TASK_QUEUED', task_id=f'task-{i}')
            emit('SUBAGENT_STARTED', task_id=f'task-{i}', worker_id=f'worker-{i%8}')
            emit('LLM_STARTED', task_id=f'task-{i}')
        for i in range(batch, min(batch+8, count)):
            task = f'task-{i}'
            parent = 'root' if i < 8 else f'candidate-{(i-8)//2}'
            candidate = Candidate(candidate_id=f'candidate-{i}', parent_candidate_id=None if parent=='root' else parent,
                strategy=f'Synthetic candidate {i}', explanation='Labeled test data, not an actual search result.', code=f'# Synthetic example\nprint({i})')
            evaluation = EvaluationResult(candidate_id=candidate.candidate_id, passed_tests=i%2, total_tests=1,
                reward=float(i%2), test_results=(), execution_time_ms=10)
            emit('LLM_FINISHED', task_id=task, input_tokens=100, output_tokens=50, cost_usd=0)
            emit('CANDIDATE_GENERATED', task_id=task, candidate_id=candidate.candidate_id, parent_id=parent, candidate=candidate.model_dump(mode='json'))
            emit('EVALUATION_STARTED', task_id=task, candidate_id=candidate.candidate_id)
            emit('CANDIDATE_EVALUATED', task_id=task, candidate_id=candidate.candidate_id, reward=evaluation.reward, evaluation=evaluation.model_dump(mode='json'))
            node=tree.add(parent,candidate,evaluation,100,task)
            emit('NODE_CREATED', node_id=node.node_id, node=node.model_dump(mode='json'))
            emit('SUBAGENT_FINISHED',task_id=task)
    while len(events)<4998:
        emit('BUDGET_RESERVATION_RECONCILED')
    emit('FINAL_SELECTED',node_id='candidate-1')
    emit('RUN_FINISHED',termination_reason='SUCCESS')
    artifacts={'tree.json':tree.model_dump(mode='json'),'problem.json':{'title':'SYNTHETIC · 500 candidate performance fixture'},
        'config.json':{'llm':{'model':'synthetic-test-data'}},'result.json':{'algorithm':'beam','termination_reason':'SUCCESS','selected_node_id':'candidate-1','visible_reward':1,
        'budget':{'llm_calls':count,'candidates':count,'input_tokens':count*100,'output_tokens':count*50,'total_tokens':count*150,'cost_usd':0,'elapsed_seconds':50}}}
    for name,data in artifacts.items():
        (directory/name).write_text(json.dumps(data))
    (directory/'events.jsonl').write_text('\n'.join(map(json.dumps,events))+'\n')
    print(directory)


if __name__=='__main__':
    generate()
