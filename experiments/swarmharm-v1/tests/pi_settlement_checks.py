"""Aborted native goals must preserve queued inputs and reachable timers."""
from copy import deepcopy
import unittest
import run

class PiSettlementChecks(unittest.TestCase):
    def base(self):
        return ({'aborted':True,'sdk_idle':True,'sdk_pending_messages':0,
            'control_epoch':3,'turn':8,'native_goal':{'goal':{'status':'blocked'}}},
            {'controller_epoch':3,'last_requested_turn':8,'controller_prompt_pending':False})

    def test_only_current_idle_blocked_or_indefinite_wait_can_settle(self):
        message,state=self.base()
        self.assertTrue(run.aborted_goal_is_idle(message,state))
        indefinite=deepcopy(message);indefinite['native_goal']['goal']={'status':'active','waiting':{'resumeAt':None}}
        self.assertTrue(run.aborted_goal_is_idle(indefinite,state))
        for patch in ({'aborted':False},{'sdk_idle':False},{'sdk_pending_messages':1},
                      {'control_epoch':2},{'turn':7},
                      {'native_goal':{'goal':{'status':'active'}}},
                      {'native_goal':{'goal':{'status':'active','waiting':{'resumeAt':999}}}},
                      {'native_goal':{'goal':{'status':'complete'}}}):
            self.assertFalse(run.aborted_goal_is_idle({**message,**patch},state),patch)
        self.assertFalse(run.aborted_goal_is_idle(message,{**state,'controller_prompt_pending':True}))
