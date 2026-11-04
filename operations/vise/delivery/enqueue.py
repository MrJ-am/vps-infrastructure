"""Publish a ViSe plan to the shared promotion queue after fresh checks.

Caller holds the shared environment lock. Existing active plans are resumed by
the promotion worker, never replaced here. No service or database operation.
"""
import contract as C,admission_orchestrator as O
import delivery_environment as E,promotion_enqueue as N
import accepted_plan as P,generation_layout as L,vise_verified_delivery as V

def publish(state,roots,jobs,acceptance,job_id,token,*,environment=E.read,observe=N.R.actual):
    plan=P.load(acceptance,jobs,job_id)
    def ready():
        C.require(P.load(acceptance,jobs,job_id)==plan,'VISE_ENQUEUE_ACCEPTANCE_CHANGED')
        C.require(environment()==plan['environment'],'VISE_ENQUEUE_ENVIRONMENT_CHANGED')
        L.verify(plan['old'],plan['new'],plan['candidate'],
            previous_adopted=plan['environment'].get('vise',{}).get('adopted'))
    return N.enqueue(state,roots,jobs,plan,authorize=lambda value:V.verify(value,token,jobs=jobs),
        ready=ready,observe=observe)
