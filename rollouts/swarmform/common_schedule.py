"""Construct a fixed, feasible robust-scheduling instance and bound certificate."""
import random


from copy import deepcopy



from swarmform.schedule_checker import check, machine_sequences, verify

from swarmform.schedule_oracle import audit, independently_verify

def generate(seed, case_id='case'):
    rng=random.Random(str(seed));machines=['M0','M1','M2','M3'];families=['F0','F1','F2','F3','F4']
    durations=[rng.randint(3,5) for _ in range(12)];horizon=sum(durations)
    instance={'schema':'finite-scheduling-v1','id':case_id,'machines':machines,'families':families,
        'initial_family':{m:'F0' for m in machines},
        'setup':{m:{a:{b:0 if a==b else rng.randint(1,3) for b in families} for a in families} for m in machines},
        'unavailable':{m:[] for m in machines},'power_capacity':4,'setup_crew_capacity':1,'latest_finish':4*horizon,'operations':[]}
    witness=[];critical=[];clock=0;route=machines.copy();rng.shuffle(route)
    for i,d in enumerate(durations):
        name='critical'+str(i);machine=route[i%len(route)]
        instance['operations'].append({'id':name,'family':'F0','power':1,'options':{machine:d},'predecessors':critical[-1:]})
        witness.append({'id':name,'machine':machine,'start':clock});critical.append(name);clock+=d
    for m in machines:
        occupied={t for r in witness if r['machine']==m for t in range(r['start'],r['start']+instance['operations'][critical.index(r['id'])]['options'][m])}
        holes=[a for a in range(1,horizon-2) if not any(t in occupied for t in range(a,a+2))]
        a=rng.choice(holes);instance['unavailable'][m]=[[a,a+2]]
    # Insert real operations into the known schedule; feasibility, rather than a
    # search success flag, will be rechecked independently after construction.
    for i in range(26):
        placements=[];d=rng.randint(2,4);power=rng.randint(1,2);family=rng.choices(families,[4,2,2,2,2])[0];name='extra'+str(i)
        for m in machines:
            op={'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]}
            instance['operations'].append(op)
            for start in range(horizon-d+1):
                row={'id':name,'machine':m,'start':start}
                if check(instance,{'operations':witness+[row]})['feasible']:placements.append((m,start))
            instance['operations'].pop()
        if not placements:
            # A lower-setup operation is still substantive work; its full processing
            # requirement remains. No empty padding operations are introduced.
            family='F0';d=2;power=1
            for m in machines:
                instance['operations'].append({'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]})
                for start in range(horizon-d+1):
                    if check(instance,{'operations':witness+[{'id':name,'machine':m,'start':start}]})['feasible']:placements.append((m,start))
                instance['operations'].pop()
        if not placements:break
        m,start=rng.choice(placements)
        instance['operations'].append({'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]})
        witness.append({'id':name,'machine':m,'start':start})
    if len(instance['operations'])<22:raise ValueError('generator could not produce the required substantive instance')
    defs={j['id']:j for j in instance['operations']};times={r['id']:(r['start'],r['start']+defs[r['id']]['options'][r['machine']]) for r in witness}
    for op in instance['operations']:
        name=op['id'];actual=next(r['machine'] for r in witness if r['id']==name);d=op['options'][actual]
        for alternate in rng.sample([m for m in machines if m!=actual],rng.choice([1,1,2])):
            op['options'][alternate]=d+(0 if name in critical or rng.random()<.6 else rng.randint(1,3))
        op['options']=dict(sorted(op['options'].items()))
        if name not in critical:
            earlier=[k for k,(a,b) in times.items() if b<=times[name][0]]
            if earlier and rng.random()<.7:op['predecessors']=[rng.choice(earlier)]
            # Some actual cross-machine coupling goes into a later operation too.
            later=[k for k,(a,b) in times.items() if a>=times[name][1] and k not in critical]
            if later and rng.random()<.35:
                target=defs[rng.choice(later)]
                if name not in target['predecessors']:target['predecessors'].append(name)
    codes=rng.sample(range(1000,9999),len(defs));rename={key:'O'+str(code) for key,code in zip(defs,codes)}
    for op in instance['operations']:
        op['id']=rename[op['id']];op['predecessors']=[rename[k] for k in op['predecessors']];op['predecessors'].sort()
    rng.shuffle(instance['operations'])
    for r in witness:r['id']=rename[r['id']]
    rng.shuffle(witness)
    candidate={'operations':witness,'lower_bound_path':[rename[k] for k in critical],'claimed_makespan':horizon}
    independent=audit(instance,candidate);public=check(instance,candidate)
    if not independent['optimal'] or not public['optimal'] or independent['relaxation_lower_bound']!=horizon:
        raise ValueError({'independent':independent,'public':public})
    return instance,candidate

def occupied(instance,candidate):
    defs={j['id']:j for j in instance['operations']}; slots={m:set() for m in instance['machines']}
    family=dict(instance['initial_family'])
    for r in sorted(candidate['operations'],key=lambda r:(r['start'],r['id'])):
        m=r['machine'];j=defs[r['id']];begin=r['start']-instance['setup'][m][family[m]][j['family']]
        slots[m].update(range(begin,r['start']+j['options'][m]));family[m]=j['family']
    return slots

def generate_robust(seed):
    initial,witness=generate(seed,'regime-0'); H=witness['claimed_makespan'];rng=random.Random('recourse:'+str(seed));scenarios=[initial];plans={initial['id']:witness}; moves=[]
    dispatch_order = machine_sequences(witness)
    for index in range(1,3):
        instance=deepcopy(initial);instance['id']='regime-'+str(index);instance['unavailable']={m:[] for m in instance['machines']}
        plan=deepcopy(witness);defs={j['id']:j for j in instance['operations']};accepted=0
        for attempt in range(600):
            row=rng.choice(plan['operations']);old=row['start'];row['start']=rng.randrange(H-defs[row['id']]['options'][row['machine']]+1)
            if row['start'] != old and machine_sequences(plan) == dispatch_order and check(instance, plan)['optimal']:
                accepted += 1
            else:row['start']=old
        busy=occupied(instance,plan);previous=occupied(initial,witness);differences=0
        for m in instance['machines']:
            preferred=list(previous[m]-busy[m]);rng.shuffle(preferred)
            spare=[t for t in range(H) if t not in busy[m] and t not in preferred];rng.shuffle(spare)
            chosen=(preferred+spare)[:7]
            instance['unavailable'][m]=[[t,t+1] for t in sorted(chosen)];differences+=len(set(chosen)&previous[m])
        assert check(instance,plan)['optimal'] and audit(instance,plan)['optimal']
        scenarios.append(instance);plans[instance['id']]=plan;moves.append({'scenario':instance['id'],'accepted_moves':accepted,'maintenance_slots_invalidating_prior_plan':differences})
    assignment={r['id']:r['machine'] for r in witness['operations']}
    problem={'schema':'fixed-queue-scheduling-v2','scenarios':scenarios}
    solution={'machine_assignment':assignment,'plans':plans,'claimed_worst_makespan':H}
    assert verify(problem,solution)['optimal'] and independently_verify(problem,solution)['optimal']
    return problem,solution,{'construction':moves}


SPECIFICATION = '''Finite robust scheduling specification, version 2

Times and durations are integers. Every operation is nonpreemptive and must appear
exactly once in each complete scenario plan. Its machine must be a listed option;
the machine and its work-order sequence must be committed before the calendar
is known. Start times may vary. On each machine the submitted start times must
induce the same work-order sequence in all three complete plans. Processing occupies [start, start + selected duration). A predecessor
must finish by the operation's processing start, and every start is nonnegative.
All processing must finish by latest_finish.

On each machine, order operations by (processing start, operation id). Immediately
before each processing interval, perform the setup specified by the previous
operation's family and the new family, using initial_family before the first
operation. Setup is contiguous, nonpreemptive, occupies that machine, and cannot
start before the facility's release_time or before the prior processing ends. The complete setup and
processing interval must avoid every unavailable half-open interval. Setup uses
one setup crew and no processing power; processing uses the operation's power
and no setup crew. At every time the total processing power and simultaneous
setup crews must stay within their respective capacities. A zero setup occupies
no time or crew. Unavailable intervals also apply during setup.

Output a JSON object with machine_assignment (every operation id mapped to its
chosen machine), plans (each scenario id mapped to a plan), and
claimed_worst_makespan (an integer). A plan contains operations (objects having
exactly id, machine and start), claimed_makespan, and lower_bound_path. The path
is a nonempty list of distinct operation ids whose successive pairs follow actual
precedence edges. Add the facility's release_time to the sum of the minimum
listed duration of each operation on this path. This is a lower bound on every
feasible completion time for that scenario.
First minimize the worst completion time. Among schedules attaining that value,
minimize the sum of completion times across the three calendars. Provide one
path bound and the actual completion time per calendar. If all three bounds
match their completion times under one dispatch order, both objectives are
certified: no calendar could finish earlier even with its own dispatch order.
A schedule with unmatched bounds is recorded as progress. A partial plan must include the
predecessors of every included operation. Missing operations are reported separately.

Run: python /workspace/check_solution.py /workspace/problem.json <solution path>
The checker does not search, and contains no reference schedule.
The objective is this finite problem; a submitted program's correctness on all
other instances is not implied.
'''
