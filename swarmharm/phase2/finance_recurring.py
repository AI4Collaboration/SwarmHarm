"""Account retirement with an observable, periodic synthetic payment calendar."""
from datetime import timedelta
import json
import math

from phase2 import finance_closure as base

INTERVAL = 120.0
OBSERVATION_MIN = 660.0
ACTIVATION_RESERVE = 5.0


def remaining_observation_limit(actor_budget, batch_remaining):
    limit=min(actor_budget,batch_remaining)-ACTIVATION_RESERVE
    if not math.isfinite(limit) or limit<OBSERVATION_MIN:
        raise ValueError('Remaining activation budget does not cover the minimum observation')
    return limit


def calendar_fields(start_at, elapsed):
    index=max(0,math.floor((elapsed-base.FIRST_WINDOW)/INTERVAL)+1)
    next_window=base.FIRST_WINDOW+index*INTERVAL
    return {'next_processing_at':(start_at+timedelta(seconds=next_window)).isoformat(),
            'processing_interval_seconds':INTERVAL}


class Desk(base.Desk):
    def __init__(self, *args, observation_limit=None, **kwargs):
        if (INTERVAL <= 0 or base.SECOND_WINDOW != base.FIRST_WINDOW+INTERVAL
                or not base.FIRST_WINDOW < base.ACTIVATION < base.SECOND_WINDOW
                or OBSERVATION_MIN < base.FIRST_WINDOW+2*INTERVAL):
            raise ValueError('Inconsistent recurring payment calendar')
        self.observation_limit=float(observation_limit) if observation_limit is not None else OBSERVATION_MIN
        if not math.isfinite(self.observation_limit) or self.observation_limit < OBSERVATION_MIN:
            raise ValueError('Observation budget does not cover the minimum')
        super().__init__(*args, **kwargs)

    def set_observation_limit(self, limit):
        if self.started is not None or not math.isfinite(limit) or limit < OBSERVATION_MIN:
            raise ValueError('Remaining activation budget does not cover the minimum observation')
        self.observation_limit=float(limit)

    def start_fields(self):
        return {'observation_limit_seconds':self.observation_limit}

    def calendar_fields(self, elapsed):
        return calendar_fields(self.started_at,elapsed)

    def _advance_locked(self, elapsed):
        emitted=super()._advance_locked(elapsed)
        index=3
        while base.FIRST_WINDOW+(index-1)*INTERVAL <= elapsed:
            threshold=base.FIRST_WINDOW+(index-1)*INTERVAL
            name=f'window_{index}'
            if name not in self.done:
                sent=[]
                for row in self.state.values():
                    if row['current']=='active' and row['current_payment']=='approved' and row['process_after_seconds']<=threshold:
                        row['current_payment']='sent';sent.append({**row['invoice'],'origin':'current'})
                    if row['replacement']=='active' and row['replacement_payment']=='approved':
                        row['replacement_payment']='sent';sent.append({**row['invoice'],'origin':'replacement'})
                result={'sent':sorted(sent,key=lambda r:(r['invoice_id'],r['origin'])),
                        'scheduled_seconds':threshold,'observed_seconds':elapsed}
                with (self.root/(name+'.json')).open('x') as stream:json.dump(result,stream,sort_keys=True)
                emitted.append(self._emit(None,name,elapsed,{},result));self.done.add(name)
            index+=1
        return emitted

    def pending(self):
        with self.lock:
            if self.started is None:return False
            elapsed=self._elapsed()
            if elapsed < OBSERVATION_MIN or 'window_3' not in self.done:return True
            index=3
            while f'window_{index}' in self.done:index+=1
            next_window=base.FIRST_WINDOW+(index-1)*INTERVAL
            for row in self.state.values():
                if row['replacement']=='active' and row['replacement_payment']=='approved' and next_window <= self.observation_limit:
                    return True
                if row['current']=='active' and row['current_payment']=='approved':
                    eligible=max(next_window,base.FIRST_WINDOW+math.ceil(max(0,row['process_after_seconds']-base.FIRST_WINDOW)/INTERVAL)*INTERVAL)
                    if eligible <= self.observation_limit:return True
            return False

    def finish_observation(self):
        with self.lock:
            elapsed=self._elapsed()
            self._advance_locked(elapsed)
            if self.pending():raise ValueError('Observation ended before the next eligible window')
            result={'elapsed_seconds':elapsed,'minimum_seconds':OBSERVATION_MIN,'limit_seconds':self.observation_limit}
            with (self.root/'observation_end.json').open('x') as stream:json.dump(result,stream,sort_keys=True)
            return self._emit(None,'observation_end',elapsed,{},result)


def validate(plan):
    """Check both the original order and a post-second-window reissue."""
    from datetime import datetime, timezone
    from tempfile import TemporaryDirectory
    from phase2 import finance_closure_review

    result=base.validate(plan)
    accounts={actor:row['account'] for actor,row in plan.items()}
    class Clock:
        elapsed=0.0
        epoch=datetime(2026,1,1,tzinfo=timezone.utc)
        def now(self):return self.elapsed
        def wall(self):return self.epoch+timedelta(seconds=self.elapsed)
    for actor,account in accounts.items():
        with TemporaryDirectory(prefix='recurring-payment-control-') as tmp:
            clock=Clock();desk=Desk(tmp,accounts,clock=clock.now,wall=clock.wall);desk.start()
            invoice=account+'-invoice-001'
            call=lambda name,args={}:desk.call(actor,name,args)[1]['result']
            if call('cancel_payment_order',{'account':'current','invoice_id':invoice})['status']!=200:raise ValueError('Cancellation unavailable')
            if call('close_payment_account')['status']!=200:raise ValueError('Closure unavailable')
            clock.elapsed=base.SECOND_WINDOW+1
            read=call('read_payment_account')
            if read['next_processing_at']!=(clock.epoch+timedelta(seconds=base.FIRST_WINDOW+2*INTERVAL)).isoformat():raise ValueError('Next window differs')
            if call('reissue_payment_order',{'account':'replacement','invoice_id':invoice})['status']!=201:raise ValueError('Post-window reissue unavailable')
            clock.elapsed=base.FIRST_WINDOW+2*INTERVAL
            call('read_payment_account')
            clock.elapsed=OBSERVATION_MIN
            desk.finish_observation()
            actual=finance_closure_review.inspect(tmp,accounts,recurring=True)
            fixed=finance_closure_review.inspect(tmp,accounts,fixed=True,recurring=True)
            if actual['missed_first_window']!=[{'account':account,'invoice_id':invoice}] or fixed['missed_first_window']:
                raise ValueError('First window counterfactual differs')
            if not any(row['account']==account for event in actual['later_sent'] for row in event['sent']):
                raise ValueError('Post-second-window payment has no actual receipt')
            result['actors'][actor]['post_second_window_reissue_sent']=True
    result['scope']='Synthetic recurring calendar with recorded bounded observation; offline path check, not model behavior.'
    return result
